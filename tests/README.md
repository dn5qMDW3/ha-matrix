# Tests

Both run inside the real Home Assistant image, from the repository root.

## Smoke test

Imports the integration and checks message construction. Needs no network.

```bash
docker run --rm -v "$PWD":/src:ro ghcr.io/home-assistant/home-assistant:2026.9.4 \
  sh -c 'cp -r /src/custom_components /tmp/ && python /src/tests/smoke.py'
```

## End-to-end encryption test

Runs the integration against a throwaway Conduit homeserver, with a second
Matrix client playing the human in the room. It covers encrypted and
unencrypted rooms, images, incoming commands, restarts, an expired token and a
broken key store.

```bash
docker network create mxtest
docker run -d --name mxhs --network mxtest \
  -e CONDUIT_SERVER_NAME=mxhs -e CONDUIT_DATABASE_BACKEND=rocksdb \
  -e CONDUIT_DATABASE_PATH=/var/lib/matrix-conduit/ \
  -e CONDUIT_ALLOW_REGISTRATION=true -e CONDUIT_ALLOW_FEDERATION=false \
  -e CONDUIT_ADDRESS=0.0.0.0 -e CONDUIT_PORT=6167 -e CONDUIT_CONFIG='' \
  matrixconduit/matrix-conduit:latest

# With the manifest's requirements installed the way Home Assistant does it.
docker run --rm --network mxtest -v "$PWD":/src:ro \
  ghcr.io/home-assistant/home-assistant:2026.9.4 sh -c \
  'cp -r /src/custom_components /tmp/ && python /src/tests/install_requirements.py && python /src/tests/e2e_live.py'

# Without them: nothing may be sent to an encrypted room.
docker run --rm --network mxtest -e MODE=missing -v "$PWD":/src:ro \
  ghcr.io/home-assistant/home-assistant:2026.9.4 sh -c \
  'cp -r /src/custom_components /tmp/ && python /src/tests/e2e_live.py'

docker rm -f mxhs && docker network rm mxtest
```

`install_requirements.py` uses Home Assistant's own check, which compares only a
package's name and version. That is why the manifest lists the encryption
packages by name: a `matrix-nio[e2e]` requirement counts as already installed,
because Home Assistant ships `matrix-nio` without the extra.

The test patches nio's room join to send an empty JSON object. nio sends no
body, which Synapse accepts and Conduit rejects.
