# Exobiology reference data

`data/exobio_data.json` is generated from
[dwomble/EDMC-ExplorerLite](https://github.com/dwomble/EDMC-ExplorerLite)
(MIT, see `data/LICENSE-ExplorerLite.txt`): species base credit values,
genus minimum sample distances, species colours, and genus/species spawn
rulesets. ExplorerLite credits the Elite Dangerous Fandom wiki
"Exobiology Sample Values and Details" page and
[njthomson/SrvSurvey](https://github.com/njthomson/SrvSurvey) for values,
and ed-dsn.net community data for spawn conditions.

Values are game facts; predictions are heuristics and can be wrong.
Regenerate with `tools/build_exobio_data.py` (TODO) when upstream updates.
