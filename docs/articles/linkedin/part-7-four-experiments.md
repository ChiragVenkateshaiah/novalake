I measured an 86% performance improvement.

It was caused by nothing at all. I nearly published it.

Part 7 of the NovaLake build log is four Spark optimization experiments on a 2,138,809-row table — and the methodology traps that sit underneath every one of them.

Here's the near-miss. I ran a baseline query: 2 files, 123,778,745 bytes, 6,831 ms. Applied `CLUSTER BY (merchant_id)`, ran OPTIMIZE, re-ran the identical query.

944 ms. Down from 6,831. An 86% improvement.

Except OPTIMIZE had reported `numFilesAdded: 0, numFilesRemoved: 0` — its own metrics explained why, `nodeMinNumFilesToCompact: 4` against `totalConsideredFiles: 2`. A 2-file table sits below the threshold Delta requires before physically rewriting anything.

Same 2 files. Same bytes, to the byte. Nothing physical changed. The 86% was a warehouse warm-up artifact from the query I'd run moments earlier.

Duration is the number that looks best in a slide. A config change and a physical effect are different things.

So I tested it properly — disposable scratch copy, force-fragmented to 8 files, then clustered. That produced a genuine rewrite (`approxClusteringQuality: 0.784`) and the real result:

Files −87.5%. Bytes −89%. Duration −11%.

At this scale, fixed per-query overhead dominates wall-clock so thoroughly that an 89% I/O reduction shows up as an 11% duration improvement. Which is exactly why an 86% duration drop with zero I/O change should have been suspicious immediately.

Two more traps from the same phase:

→ Databricks' result cache matches on logical result equivalence, not literal query text. A join hint doesn't change declarative semantics — so all three of my join-strategy variants were "the same query" to the cache, and two of them were silently served from the first one's result. `SET use_cached_result = false` per call did nothing, because each API call is its own stateless session.

→ Predictive Optimization was active on my workspace and completely invisible to `SHOW TBLPROPERTIES`. It had already compacted the exact table I was benchmarking, earlier the same day. If you're measuring file layout and not checking that system table, your "before" can change under you.

The phase opened with a bug that duplicated 122,592 rows. Two failing tests shared the identical count; duplicates started exactly at page 401, a clean 400-page range. Not random corruption — an overlap.

The generator never cleared its output directory. This run wrote 20 files; the pilot had written 40 at the same path. The pilot's higher-indexed files survived, and Spark's directory scan happily read all 40.

Also: never trust a "before" measurement that ran first in a session. Confirmed three separate times.

Part 7 of 8 → LINK-PART-7

#ApacheSpark #Databricks #DeltaLake #Performance #DataEngineering
