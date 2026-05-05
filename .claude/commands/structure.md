# /structure

Print the current project folder structure, excluding noise.

Run this command in the project root:

```bash
find . -type f \
  -not -path './venv/*' \
  -not -path './node_modules/*' \
  -not -path './.git/*' \
  -not -path './cdk.out/*' \
  -not -path './__pycache__/*' \
  -not -path './*.egg-info/*' \
  | sort \
  | tree --fromfile
```

If `tree` is not installed, fallback:

```bash
find . -type f \
  -not -path './venv/*' \
  -not -path './node_modules/*' \
  -not -path './.git/*' \
  -not -path './cdk.out/*' \
  -not -path './__pycache__/*' \
  | sort
```

Output the result and summarize how many files per top-level folder.