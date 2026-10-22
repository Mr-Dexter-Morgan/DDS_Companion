# One real Windows validation — pending separate authorization

This file is a test plan, not an instruction already executed on a user computer.
Use the existing Windows build_windows.bat workflow to produce native x64 binaries
from this exact committed source. Check DDS.exe, DDSApp.exe, DDSUpdater.exe file/
product version 0.8.6 and the About page. Use linked DDS Plugin 0.5.4.
Do not reset the archive/cache or modify Installer to validate this patch.

1. With authorized candidate activation, confirm Plugin heartbeat and normal capture
   still work; Companion reads the same existing DataRoot. Record total/known/cache/
   awaiting counts and the six affected IDs. Do not modify them by SQL.
2. For the historical deleted voice source, verify channel.json guildId/id/type and
   whether Discord audit log has CHANNEL_DELETE for that exact ID. The logged-in
   user needs audit-log access. Restart Plugin once; observe the bounded check.
3. If positive proof is found, inspect source_evidence.json, Companion evidence row,
   and media state. Expected reproducer: total147/known141/cache29/awaiting0/
   SOURCE_GONE6. All metadata/relations and the 29 cached files remain intact.
4. If no positive proof exists/access is unavailable, expected result is unchanged
   awaiting6/UNKNOWN. Record the limitation; never claim this reproducer fixed.
5. Press Retry All repeatedly. SOURCE_GONE stays terminal, attempts do not increase,
   no download is queued for those objects. Restart Companion: state persists.
6. Open an existing text channel and an existing voice/stage source with an expired
   attachment; fresh normal capture still recovers the same identity and caches it.
7. In an authorized disposable channel owned for this test, capture a voice or stage
   attachment and then have its owner delete the channel. Verify positive audit
   evidence, terminal classification after URL expiry, and cached-file priority.
   Do not delete an existing working channel to create the test.
8. Confirm a missing guild, logout/reconnect or inaccessible channel never creates
   proof; unsupported audit permissions leave UNKNOWN. Record actual HTTP module
   resolution/response shape. A missing adapter is a live defect to fix, not PASS.

Full live PASS requires the real evidence adapter to work and the target scenario
to produce the expected states. No such live PASS is claimed by this candidate.
