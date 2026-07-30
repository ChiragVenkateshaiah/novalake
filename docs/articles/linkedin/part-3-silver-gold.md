One missing keyword would have silently deleted 18-19% of my transactions.

No error. No warning. Just a smaller table.

Part 3 of the NovaLake build log covers Silver and Gold — 81 dbt models in the largest phase of the project, then 20 more to conform them.

The keyword was `OUTER`.

Arrays in this dataset come in three flavours: populated, genuinely empty (`[]`), and missing entirely (null). Plain `posexplode` drops the row when the array is empty or null. `LATERAL VIEW OUTER posexplode` keeps it.

Guaranteed-non-empty arrays got plain `posexplode`. Everything else got `OUTER`. The difference between those two decisions is a fifth of the table.

Three more ways the same phase could have silently corrupted rows:

→ FX direction. The source carries `{base: USD, quote: X, rate: R}`, meaning 1 USD = R units of X. Converting quote→USD therefore *divides*. Getting it backwards produces plausible-looking numbers wrong by orders of magnitude, and never errors. Also: the generator emits no rate row for USD itself, so this is a LEFT JOIN with `coalesce(rate, 1.0)`. An INNER JOIN here silently deletes every USD transaction.

→ A join at the wrong grain fans out both sides. Caught in review by pre-aggregating each side to page grain first.

→ Reconciling against the wrong count would have mixed the generator's intentional delta with an unrelated 1.4% dedup effect — a "discrepancy" that was really two effects stacked.

The architectural decision that shaped everything: the two source pipelines stay completely parallel and never unify until Gold. They describe the same business events, but they have no shared ingested_at, structurally incompatible payload shapes, and different dedup tie-breaks. Forcing them into one pipeline means a union of every difference, defended by CASE expressions, at every stage.

And the verification I now use by default for any refactor:

Increment 0 refactored a model onto a new generic layer. Row counts matched. All tests passed.

That proves nothing. A refactor can preserve row count and test outcomes while corrupting values inside rows.

So: a full-row EXCEPT diff in both directions, before vs after. 0 rows either way.

Gold added the rule that a coincidentally-similar field is not a foreign key. Two columns looked exactly like FKs. They're independently-generated random UUIDs. Joining on them returns a technically-valid, nearly-empty result set that looks like a real finding.

Part 3 of 8 → LINK-PART-3

#dbt #DataEngineering #Databricks #SQL #DataModeling
