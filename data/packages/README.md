# Downloadable wheel

Download [`radaccord-1.2.0rc3-py3-none-any.whl`](radaccord-1.2.0rc3-py3-none-any.whl).

SHA-256: `1976dc89877a7bed5b93dbad8fbbcf33dc4bc1bb25e781ed04a7d2e6b86644a6`.

For offline installation, first prepare a compatible environment containing the required dependencies. This wheel contains RadAccord code; it does not bundle NumPy, NiBabel or optional radiomics engines. From the source-release root:

```sh
python -m pip install --no-index --no-deps data/packages/radaccord-1.2.0rc3-py3-none-any.whl
python -m pip check
python -m radaccord version
python -m radaccord demo --output ./offline-demo
```

Use a fresh output directory for the synthetic demo. If `pip check` reports missing dependencies, supply their compatible wheels separately before running RadAccord. See the [installation guide](../../docs/INSTALL.md) for dependency versions, separate native-engine environments and full instructions. This local release candidate is not a claim of PyPI publication.
