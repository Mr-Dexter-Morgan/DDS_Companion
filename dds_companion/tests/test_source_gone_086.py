from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from dds_companion import __version__
from dds_companion.core.settings import CompanionSettings
from dds_companion.services.import_service import ImportService
from dds_companion.services.library_service import LibraryService
from dds_companion.services.media_backfill_service import DownloadOutcome, MediaBackfillService
from dds_companion.services.media_registry_service import MediaRegistryService
from dds_companion.services.source_evidence_service import SourceEvidenceService
from dds_companion.services.stats_service import collect_stats
from dds_companion.storage.database import connect_database
from dds_companion.tests.test_imports import sample_capture
from dds_companion.watcher.capture_watcher import CaptureWatcher

GUILD = '111111111111111111'
CHANNEL = '222222222222222222'
KEY = 'attachment:666666666666666666'
OLD_URL = 'https://cdn.discordapp.com/attachments/1/2/image.png?ex=1'
NEW_URL = 'https://cdn.discordapp.com/attachments/1/2/image.png?ex=ffffffff&is=new'
DELETED_AT = datetime(2026, 9, 14, tzinfo=timezone.utc)
ENTRY = str((int(DELETED_AT.timestamp() * 1000) - 1420070400000) << 22)


class SourceGone086Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / 'db.sqlite3'
        self.conn = connect_database(self.db)
        self.data = self.root / 'DDS_Data'
        self.base = self.data / 'guilds' / GUILD / 'channels' / CHANNEL
        self.base.mkdir(parents=True)
        self.path = self.base / 'capture.json'
        self.evidence_path = self.base / 'source_evidence.json'
        self.importer = ImportService(self.conn)
        self.registry = MediaRegistryService(self.conn)
        self.service = MediaBackfillService(self.conn, self.root / 'media', transport=lambda *a: self.fail('unexpected network request'))

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def capture(self, channel_type=2, *, url=OLD_URL, captured_at='2026-09-13T12:00:00Z', message_id=None, channel_id=CHANNEL):
        data = sample_capture()
        data['channel']['type'] = channel_type
        data['channel']['id'] = channel_id
        data['capturedAt'] = captured_at
        message = data['messages'][0]
        message['channelId'] = channel_id
        if message_id:
            message['id'] = message_id
        message['attachments'][0]['url'] = url
        self.path.write_text(json.dumps(data))
        self.importer.import_file(self.path)
        return data

    def unresolved(self):
        self.service._apply_outcome(DownloadOutcome(media_key=KEY, state='UNRESOLVED', error='expired'))

    def evidence(self, channel_type=2, **overrides):
        data = dict(schemaVersion=1, availability='GONE_VERIFIED', kind='discord-audit-log-channel-delete',
                    guildId=GUILD, channelId=CHANNEL, channelType=channel_type,
                    observedAt='2026-09-14T00:01:00Z',
                    auditEntry={'id': ENTRY, 'target_id': CHANNEL, 'action_type': 12,
                                'changes': [{'key': 'type', 'old_value': channel_type}]})
        data.update(overrides)
        self.evidence_path.write_text(json.dumps(data))
        return self.importer.import_file(self.evidence_path)

    def state(self):
        return self.registry.get(KEY).state

    def test_A_B_C_existing_or_unknown_sources_keep_rediscovery(self):
        for channel_type in (0, 2, 13):
            with self.subTest(channel_type=channel_type):
                self.capture(channel_type)
                self.unresolved()
                with self.conn:
                    SourceEvidenceService(self.conn).apply_verified()
                self.assertEqual(self.state(), 'UNRESOLVED')
                self.assertEqual(self.service.counts()['unresolved'], 1)

    def test_D_E_positive_voice_and_stage_proof_preserves_metadata(self):
        for channel_type in (2, 13):
            with self.subTest(channel_type=channel_type):
                self.conn.execute('DELETE FROM source_channel_evidence')
                self.capture(channel_type, url=NEW_URL if channel_type == 13 else OLD_URL)
                before = dict(self.conn.execute('SELECT * FROM attachments').fetchone())
                self.unresolved()
                self.evidence(channel_type)
                self.assertEqual(self.state(), 'SOURCE_GONE')
                self.assertEqual(dict(self.conn.execute('SELECT * FROM attachments').fetchone()), before)
                self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM media_refs').fetchone()[0], 1)
                self.assertEqual(self.registry.get(KEY).current_url, before['url'])
                counts = self.service.counts()
                self.assertEqual((counts['total'], counts['known'], counts['unresolved'], counts['attention'], counts['source_gone']), (1, 0, 0, 0, 1))
                stats = collect_stats(self.conn, self.db, self.data)
                self.assertEqual((stats['media_unresolved'], stats['media_source_gone']), (0, 1))
                branch = LibraryService(self.conn).snapshot()[0]
                self.assertEqual((branch['media_unresolved'], branch['media_source_gone']), (0, 1))

    def test_F_G_H_no_negative_store_or_access_evidence_accepted(self):
        self.capture()
        self.unresolved()
        for overrides in ({'availability': 'UNKNOWN'}, {'kind': 'channel-store-absent'},
                          {'auditEntry': {}}, {'auditEntry': {'id': ENTRY, 'target_id': CHANNEL, 'action_type': 85}},
                          {'channelId': '333'}, {'guildId': '444'}, {'channelType': 0},
                          {'auditEntry': {'id': ENTRY, 'target_id': CHANNEL, 'action_type': 12, 'changes': [{'key': 'type', 'old_value': 13}]}}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError): self.evidence(**overrides)
                self.assertEqual(self.state(), 'UNRESOLVED')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM source_channel_evidence').fetchone()[0], 0)

    def test_wrong_persisted_source_type_cannot_be_promoted(self):
        self.capture(0)
        self.unresolved()
        self.evidence(2)
        self.assertEqual(self.state(), 'UNRESOLVED')

    def test_I_cached_file_wins_over_deleted_source(self):
        self.capture()
        media = self.root / 'media' / 'image.png'
        media.parent.mkdir()
        media.write_bytes(b'image')
        self.conn.execute("UPDATE media_objects SET state='CACHED', local_relpath='image.png', local_size=5")
        self.conn.commit()
        self.evidence()
        self.assertEqual(self.state(), 'CACHED')
        self.service.plan(CompanionSettings())
        self.assertEqual(self.state(), 'CACHED')
        self.assertEqual(media.read_bytes(), b'image')

    def test_J_retry_never_requeues_or_increments_terminal_object(self):
        self.capture()
        self.unresolved()
        self.evidence()
        attempts = self.registry.get(KEY).attempt_count
        for _ in range(3):
            self.assertFalse(self.registry.prepare_manual_retry(KEY))
            self.assertIsNone(self.service.retry_media_once(KEY, CompanionSettings()))
            self.service.plan(CompanionSettings())
            self.registry.normalize_expired_urls()
            self.registry.clear_processed_issues()
        self.assertEqual((self.state(), self.registry.get(KEY).attempt_count), ('SOURCE_GONE', attempts))
        self.assertEqual(self.service.issue_items(), [])
        self.assertEqual(self.registry.rediscovery_items(), [])

    def test_K_fresh_valid_changed_capture_recovers_but_replays_do_not(self):
        self.capture()
        self.unresolved()
        self.evidence()
        self.capture(captured_at='2026-09-13T12:01:00Z', url=NEW_URL)
        self.assertEqual(self.state(), 'SOURCE_GONE')
        self.capture(captured_at='2026-09-14T00:02:00Z')
        self.assertEqual(self.state(), 'SOURCE_GONE')
        self.capture(captured_at='2026-09-14T00:02:00Z', url=NEW_URL)
        self.assertEqual(self.state(), 'KNOWN')
        self.assertEqual(self.registry.get(KEY).attempt_count, 0)
        self.service.plan(CompanionSettings())
        self.assertEqual(self.state(), 'QUEUED')

    def test_L_migration_restart_and_old_records_do_not_guess_deletion(self):
        self.capture()
        self.unresolved()
        self.conn.close()
        self.conn = connect_database(self.db)
        self.assertEqual(self.conn.execute('SELECT state FROM media_objects').fetchone()[0], 'UNRESOLVED')
        self.importer = ImportService(self.conn)
        self.evidence()
        self.conn.close()
        self.conn = connect_database(self.db)
        self.assertEqual(self.conn.execute('SELECT state FROM media_objects').fetchone()[0], 'SOURCE_GONE')
        self.assertEqual(self.conn.execute('SELECT value FROM schema_meta WHERE key="schema_version"').fetchone()[0], '5')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM attachments').fetchone()[0], 1)

    def test_evidence_before_expiry_and_before_capture_is_order_independent(self):
        self.evidence()
        self.capture()
        self.assertEqual(self.state(), 'KNOWN')
        self.unresolved()
        self.assertEqual(self.state(), 'SOURCE_GONE')
        self.assertEqual(self.evidence().skipped_unchanged, 1)

    def test_shared_attachment_with_other_live_reference_stays_recoverable(self):
        self.capture()
        self.capture(0, message_id='777777777777777777', channel_id='888888888888888888')
        self.unresolved()
        self.evidence()
        self.assertEqual(self.state(), 'UNRESOLVED')

    def test_sidecar_live_watcher_settles_and_reset_boundary_is_respected(self):
        self.capture()
        self.unresolved()
        watcher = CaptureWatcher(self.data, self.importer, self.conn, settle_seconds=0.05)
        watcher.prime()
        # Produce evidence without importing it directly, as Plugin does.
        original = self.importer.import_file
        self.importer.import_file = lambda _: None
        self.evidence()
        self.importer.import_file = original
        watcher.scan_once(now=0)
        events = watcher.scan_once(now=1)
        self.assertTrue(any(e.kind == 'imported' for e in events))
        self.assertEqual(self.state(), 'SOURCE_GONE')
        boundary = ImportService(self.conn, capture_not_before_ns=self.evidence_path.stat().st_mtime_ns)
        self.assertEqual(boundary.import_file(self.evidence_path).skipped_before_boundary, 1)

    def test_export_preserves_source_gone_metadata_without_retry_label(self):
        import zipfile
        from dds_companion.services.export_package_service import ExportPackageService
        self.capture()
        self.unresolved()
        self.evidence()
        result = ExportPackageService(self.conn, self.root / 'media').package(
            'channel', CHANNEL, mode='TEXT_AND_CACHE', output_dir=self.root / 'exports', app_version=__version__)
        with zipfile.ZipFile(result.output_path) as archive:
            item = json.loads(archive.read('media_index.json'))[0]
            self.assertEqual(item['package_state'], 'source_gone')
            self.assertEqual(item['media_state'], 'SOURCE_GONE')
            self.assertEqual(item['url'], OLD_URL)
            self.assertIn(b'source_gone', archive.read('content.md'))
        self.assertEqual(self.state(), 'SOURCE_GONE')

    def test_full_scan_discovers_positive_sidecar_and_unchanged_replay_is_quiet(self):
        self.capture()
        self.unresolved()
        self.evidence()
        self.conn.execute("UPDATE media_objects SET state='UNRESOLVED'")
        self.conn.commit()
        result = self.importer.import_all(self.data)
        self.assertEqual(result.files_seen, 2)
        self.assertEqual(result.failed, 0)
        self.assertEqual(self.state(), 'SOURCE_GONE')
        self.assertEqual(self.evidence().skipped_unchanged, 1)

    def test_gui_detail_and_library_show_terminal_state_passively(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication, QLabel
        from dds_companion.gui.pages import LibraryPage
        app = QApplication.instance() or QApplication([])
        page = LibraryPage()
        page._media_root = self.root / 'media'
        widget = page._attachment_widget({'filename': 'image.png', 'media_state': 'SOURCE_GONE'})
        labels = [label.text() for label in widget.findChildren(QLabel)]
        self.assertTrue(any('Источник удалён' in label for label in labels))
        self.assertIn('Источник удалён: 1', page._media_tooltip({'media_source_gone': 1}))
        page.close()

    def test_reproducer_147_141_29_6_counts(self):
        voice = self.capture()
        attachment = voice['messages'][0]['attachments'][0]
        voice['messages'][0]['attachments'] = [dict(attachment, id=str(660000000000000000+i)) for i in range(6)]
        voice['captureRevision'] += 1
        self.path.write_text(json.dumps(voice))
        self.importer.import_file(self.path)
        text = copy.deepcopy(voice)
        text['channel'].update(id='888888888888888888', type=0)
        text['messages'][0].update(id='777777777777777777', channelId='888888888888888888')
        text['messages'][0]['attachments'] = [dict(attachment, id=str(670000000000000000+i), url=NEW_URL) for i in range(141)]
        self.path.write_text(json.dumps(text))
        self.importer.import_file(self.path)
        self.conn.execute("UPDATE media_objects SET state='UNRESOLVED' WHERE attachment_id LIKE '660%'")
        keys = [row[0] for row in self.conn.execute("SELECT media_key FROM media_objects WHERE attachment_id LIKE '670%' LIMIT 29")]
        self.conn.executemany("UPDATE media_objects SET state='CACHED' WHERE media_key=?", [(key,) for key in keys])
        self.conn.commit()
        counts = self.service.counts()
        self.assertEqual(tuple(counts[k] for k in ('total', 'known', 'cached', 'unresolved')), (147, 141, 29, 6))
        self.evidence()
        counts = self.service.counts()
        self.assertEqual(tuple(counts[k] for k in ('total', 'known', 'cached', 'unresolved', 'source_gone')), (147, 141, 29, 0, 6))

    def test_M_authoritative_version_is_086(self):
        import tomllib
        from tools.generate_windows_version_info import render_version_info
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(__version__, '0.8.6')
        self.assertEqual(tomllib.loads((root / 'pyproject.toml').read_text())['project']['version'], __version__)
        metadata = render_version_info(description='DDS', internal_name='DDS', filename='DDS.exe')
        self.assertIn('0.8.6', metadata)
        self.assertIn('(0, 8, 6, 0)', metadata)
