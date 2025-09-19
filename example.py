from lap_notebook.resolver import PipelineCfg, Meta, LapResolver

cfg  = PipelineCfg.from_file("/humgen/diabetes/users/chase/lap/projects/pigean/config/validation.cfg")
meta = Meta.from_file("/humgen/diabetes/users/chase/lap/projects/pigean/config/validation.prod.meta")

resolver = LapResolver(cfg, meta)

# 1) List all file keys defined in the cfg
print(len(cfg.files), "file keys")
print(list(cfg.files.keys())[:10])

# 2) Get all absolute paths for a key
all_paths = resolver.get("geneset_list_stats_file")
for p in all_paths[:5]:
    print(p)

# 3) Filter by any @placeholder (with or without '@')
paths_filtered = resolver.get("geneset_list_stats_file", validation="geneset_analysis")
print(paths_filtered)

# 4) If you want extra context (placeholders, class level, whether it came from a meta override)
records = resolver.records("models_config_file", validation="geneset_analysis")
for r in records:
    print(r["path"], r["placeholders"], r["source"])
