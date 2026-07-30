My schema-drift audit reported zero findings for one whole category.

The category wasn't clean. The check was broken.

Part 2 of the NovaLake build log is about Bronze — the layer where the tooling tells you everything is fine and isn't.

First thing worth knowing: `_corrupt_record` was absent entirely from Spark's inferred schema. Zero syntactically broken lines.

That is not the good news it looks like.

PERMISSIVE mode and `_corrupt_record` protect you from *syntactic* corruption — a line that isn't valid JSON. This dataset's entire problem is *semantic* type drift: every record is perfectly valid JSON that disagrees with its neighbours about what type a field is. Permissive mode is structurally blind to that.

So I built a general-purpose shape profiler instead. Flatten the inferred schema to leaf fields, filter to StringType leaves (Spark collapses genuinely mixed-type fields to string — the string type is the tell), classify each leaf's actual values by shape, flag anything with more than one.

It found two genuine collapses, and they are not the same kind of problem:

→ `payload.risk` is destructive. A 3% minority of malformed rows forced the 97% well-formed majority to lose its struct type too, because no column type holds both a struct and a string. Recovering it needs `from_json` with an explicit schema.

→ `payload.amount_minor` is non-destructive. Int vs string. `try_cast` recovers it either way.

Conflating those two is how you write a fix that silently destroys data.

And then the honest part. My audit tool had bugs of its own.

Its null filter compared against the string "null" while the data contained "Null". Python string comparison is case-sensitive, the filter silently never fired, and it produced 46 false positives. I only caught it by checking the audit's output against the generator's known injected counts.

A second one is still in the notebook: the `json_array` branch reuses the same regex as `json_object`. It's dead code. `json_array` never matched anything, ever.

An audit tool that reports zero findings for a category can mean the category is clean, or it can mean the check is broken. From the outside those look identical.

Part 2 also covers the moment an AI code review suggested adding `.cache()` before a trailing `count()` — the idiomatic Spark move, the advice you'd give in an interview, correct on a normal cluster.

The next real run failed instantly. Databricks serverless doesn't support `cache()` at all.

Part 2 of 8 → LINK-PART-2

#Databricks #ApacheSpark #DataEngineering #DataQuality #PySpark
