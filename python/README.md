# tabula-java

Python package that bundles `tabula-java` with a minimized JRE and exposes a `tabula-java` CLI.

## Local wheel build

From repository root:

```bash
mvn --batch-mode compile assembly:single -Dmaven.test.skip=true
python -m pip install -U build
python python/scripts/prepare_bundle.py
python -m build python
```

## Release wheels with cibuildwheel

Use `.github/workflows/pypi.yml`.
