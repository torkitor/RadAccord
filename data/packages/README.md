# Downloadable wheel

Download [`radaccord-1.3.0rc1-py3-none-any.whl`](radaccord-1.3.0rc1-py3-none-any.whl).

SHA-256: `f58e91262f56890fe8b330fecf38bcc5cb43179bd95ff3d8f40ec299dea170f7`.

For offline installation, first prepare a compatible environment containing the required dependencies. This wheel contains RadAccord code; it does not bundle NumPy, NiBabel or optional radiomics engines. From the source-release root:

```sh
python -m pip install --no-index --no-deps data/packages/radaccord-1.3.0rc1-py3-none-any.whl
python -m pip check
python -m radaccord version
python -m radaccord demo --output ./offline-demo
```

Use a fresh output directory for the synthetic demo. If `pip check` reports missing dependencies, supply their compatible wheels separately before running RadAccord. See the [installation guide](../../docs/INSTALL.md) for dependency versions, separate native-engine environments and full instructions. This local release candidate is not a claim of PyPI publication.

The previous [1.2.0rc3 wheel](radaccord-1.2.0rc3-py3-none-any.whl) remains unchanged for historical use.
