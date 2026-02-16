# Data Folder

Place source files here for pipeline execution.

Required files:
- Raw polling workbook (`.xlsx`) with sheets:
  - `정당지지도 (25.1.1~12.31.)`
  - `정당지지도 (26.1.1~)`
- Pollster accuracy workbook (`.xlsx`) with columns:
  - `조사기관`
  - `MAE` (or any column containing `MAE` in its name)

You can use any filenames.
`src/pipeline.py` auto-detects files in this directory,
or pass explicit names with:

```bash
.venv/bin/python src/pipeline.py --input-xlsx <raw.xlsx> --mae-xlsx <mae.xlsx>
```
