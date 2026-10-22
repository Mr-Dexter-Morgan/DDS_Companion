# DDS Companion 0.8.6 — SOURCE_GONE lifecycle

Baseline: accepted 0.8.5, commit `66e730de44a60e531b00f7e981b62ec6c6bb27f8`.
Plugin baseline: 0.5.3, `88e763c47f17b3b52ed3f8d1103227aefc854009`.
Companion remains owner of persistent media lifecycle. Plugin supplies Discord evidence.

## Root cause

`MediaBackfillService._download_one` classifies expired Discord CDN URLs as
`UNRESOLVED` (AWAITING REDISCOVERY). `_apply_outcome` clears the dead registry URL.
`normalize_expired_urls` handles old STALE_URL rows similarly. Before this patch,
only fresh `register_attachment` observations could restore a source; the contract
contained no positive channel-deletion evidence, so genuinely deleted sources
could wait forever. Original attachment metadata remains in `attachments`.

## Positive evidence gate

The existing Plugin exports channel.json with guildId/id/type, capture-v2 message
snapshots, and plugin-heartbeat-v1; its GuildStore/ChannelStore cannot prove deletion
from an absent entry. Internal CHANNEL_DELETE dispatch provenance is not guaranteed
by baseline code, so it is only an optional hint to perform an audit lookup.

Plugin 0.5.4 reads at most one page (100 CHANNEL_DELETE entries) per eligible archived
guild per Plugin start, at most 10 guilds. One check runs five seconds after start;
CHANNEL_DELETE hints can schedule a check for guilds not already checked. There is
no recurring polling, pagination, hidden message-history fetch, or automatic retry.
The native Discord client HTTP module is feature-detected with BdApi.Webpack;
no credentials are extracted. Unavailable adapters, stores, access, audit rights,
HTTP errors, missing entries, or a presently visible channel all leave UNKNOWN.

A successful guild-scoped audit-log response must contain action_type CHANNEL_DELETE
(12) and target_id exactly matching the archived channel ID. Archived type must be
GUILD_VOICE (2) or GUILD_STAGE_VOICE (13); any audit type change must agree. Stage
instance deletion (85) is not channel deletion. These are named Discord API enum
constants because baseline has no reusable enum module.

Plugin writes `guilds/<guildId>/channels/<channelId>/source_evidence.json` atomically
using the existing writer. Envelope: schemaVersion 1, availability GONE_VERIFIED,
kind discord-audit-log-channel-delete, guildId, channelId, channelType, observedAt,
pluginVersion, auditEntry {id,target_id,action_type,changes:[type only]}.
No actor, reason, or unrelated audit entry is exported. Repeated proof is not rewritten.
Capture schema 2 and storage layout remain compatible; manifest adds source-evidence-v1.

## Persistent transition and safety

SQLite V5 adds only `source_channel_evidence`; it does not rewrite old media rows.
ImportService and settled CaptureWatcher read the sidecar alongside captures and
respect the existing archive-reset boundary. Companion validates IDs, path, type,
audit action/target and time; deletion time is derived from the audit snowflake.
Evidence can arrive before or after capture/expiry and survives restart.

Only UNRESOLVED/STALE_URL media with every archived message reference positively
verified against its persisted voice/stage source becomes SOURCE_GONE. An ordinary
text reference or any reference without matching proof prevents the terminal transition.
Cached, queued, in-flight, and usable known media are not terminalized by evidence.
The normal cache reconciliation and successful download paths retain priority.

No archive row, relation or cached file is removed. Attachment IDs, messages,
channels, timestamps and original URLs remain archived. Last-known attachment URLs
are also retained in the terminal registry record for diagnostics. SOURCE_GONE is
excluded from known/actionable/awaiting counts and has a separate passive counter,
Dashboard row, Library/detail labels and export package_state source_gone.
Retry/Retry All, clear-processed, expired-URL normalization and normal planning do
not queue SOURCE_GONE or increment attempts. Its activity event is informational.

A real capture can recover the same identity to KNOWN only with a changed, usable
Discord attachment URL and a capture timestamp newer than relevant deletion proof
(or the terminal transition if the capture supplies a different source). Old capture
replay, unchanged/dead URLs and Retry cannot recover it. Other media behavior is unchanged.

## Limits and rollback

Discord audit logs require VIEW_AUDIT_LOG and retain entries for 45 days. A bounded
first-page read may miss older deletions. In those cases DDS deliberately leaves
UNRESOLVED; there is no safe automatic classification of the historical six files
without additional positive evidence. No live Discord adapter validation was run.

0.8.5 can still read archive tables/metadata, but does not understand SOURCE_GONE
semantics and may reclassify it on recapture. Writing the candidate database with
0.8.5 is not a supported lifecycle rollback. No user database was migrated here.

Official references:
- https://docs.discord.com/developers/resources/audit-log
- https://docs.discord.com/developers/resources/channel#channel-object-channel-types
- https://docs.discord.com/developers/events/gateway-events#channel-delete
- https://docs.betterdiscord.app/api/webpack
