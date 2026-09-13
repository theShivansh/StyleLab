"""Private object storage, and the two ways an image gets referenced.

## The storage abstraction

`ObjectStore` is the seam docs/ARCHITECTURE.md section 4 asks for. `LocalObjectStore` writes
to a private directory; `DatabaseObjectStore` writes to a table. Nothing above this module
knows which one it holds, and `STORAGE_BACKEND` is how a deployment says.

A bucket-backed store is still the destination (blocker B20) and still does not exist. The
database one arrived in S13 for a narrower reason: the deployment target scales to zero and
replaces containers, so `LocalObjectStore` there is not a weaker choice but an incorrect one
— the wardrobe rows outlive the photographs they point at.

Storage keys are derived from the owner and the asset id, never from the uploaded filename.
A filename is user input, and user input that becomes a filesystem path is how a wardrobe
photo gets written to `../../app/config.py`. `_safe_segment` is the only thing that
constructs a path component, and it accepts nothing but the characters it produced.

## Two references, one Protocol

The vision adapter needs a reference the *provider* can fetch. The browser needs a
reference *it* can fetch. They are not the same problem and this module answers both:

- **`InlineImageSource`** — a `data:` URL. What a local deployment must use, because Groq's
  servers cannot reach `localhost` and the storage directory is private. Nothing to leak:
  the bytes live in the request body and there is no URL afterwards.
- **`SignedUrlImageSource`** — a signed URL against a store that issues them, for a hosted
  deployment. Still unimplemented: neither store here can issue one.
- **`browser_image_url`** — the `image_url` in an item payload. A path-embedded HMAC token
  over this API's own asset route.

## Why the browser token is in the path, not the query string

docs/SECURITY-PRIVACY.md: signed URLs are "never logged, never sent to analytics, never
placed in a query string". Object stores conventionally put the token in the query string,
which would put this project in the position of arguing with its own spec over what the
sentence meant.

It does not have to. `/assets/{asset_id}/{token}` satisfies the rule literally, works in an
`<img src>` cross-origin with no cookie, and needs no `SameSite` relaxation. The token is
capability-only and short-lived: it names one asset, it is signed for the `image` purpose
so a session token cannot be substituted, and it is minted fresh each time an item is read.
"""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AssetBlobRow
from app.security.identity import IMAGE_PURPOSE
from app.security.tokens import TokenSigner
from app.services.images import analysis_variant

logger = logging.getLogger("stylelab.storage")

#: Storage keys are built from these characters only, and validated against the same set on
#: the way back in. An uploaded filename never becomes a path.
_SAFE = re.compile(r"^[A-Za-z0-9_-]+$")


class StorageError(Exception):
    """The store could not satisfy a read or a write. Never carries a filesystem path."""


@runtime_checkable
class ObjectStore(Protocol):
    """Private image storage. Never a public bucket (docs/SECURITY-PRIVACY.md)."""

    async def put(self, key: str, data: bytes, *, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...


def storage_key(user_id: str, asset_id: str, *, extension: str) -> str:
    """The key for one asset. Derived, never supplied.

    Namespaced by user so a listing of the directory is a listing of separate wardrobes,
    and so a bug in one user's path cannot resolve into another's.
    """
    return f"{_safe_segment(user_id)}/{_safe_segment(asset_id)}.{_safe_segment(extension)}"


_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
}


def extension_for(mime_type: str) -> str:
    return _EXTENSIONS.get(mime_type, "bin")


def validated_key(key: str) -> tuple[str, str]:
    """Split a storage key into its two segments, refusing anything malformed.

    Shared by both stores rather than reimplemented in each. The filesystem store needs it
    because a key becomes a path; the database store needs it because a key becomes a primary
    key, and a store that will persist whatever string it is handed is a store that can be
    made to hold rows nothing will ever read or delete.
    """
    parts = key.split("/")
    if len(parts) != 2:
        raise StorageError("malformed storage key")

    user_part, file_part = parts
    stem, _, extension = file_part.rpartition(".")
    _safe_segment(user_part)
    _safe_segment(stem)
    _safe_segment(extension)
    return user_part, file_part


def _safe_segment(value: str) -> str:
    if not value or not _SAFE.match(value):
        raise StorageError("storage key segments are restricted to [A-Za-z0-9_-]")
    return value


class LocalObjectStore:
    """`ObjectStore` over a private directory.

    Synchronous filesystem calls inside `async def`: the writes are a couple of megabytes to
    a local disk and moving them to a thread pool would cost more in machinery than it saves
    in latency. The method signatures are async because the Protocol is, and because the
    Supabase implementation will genuinely be.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write then replace, so a reader never sees a half-written photograph.
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_bytes(data)
        temporary.replace(path)
        logger.info("stored asset", extra={"bytes": len(data), "content_type": content_type})

    async def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except OSError as error:
            raise StorageError("stored image could not be read") from error

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    async def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def _path(self, key: str) -> Path:
        """Resolve a key under the root, refusing anything that escapes it.

        Every segment is re-validated rather than trusted because it came from
        `storage_key`: this method is the one that touches the filesystem, and a check
        placed anywhere else is a check someone can route around.
        """
        user_part, file_part = validated_key(key)
        candidate = (self._root / user_part / file_part).resolve()
        if not candidate.is_relative_to(self._root):
            raise StorageError("storage key escapes the storage root")
        return candidate


class DatabaseObjectStore:
    """`ObjectStore` over a table, for deployments with no durable filesystem.

    The same four methods and the same keys as `LocalObjectStore`; a caller cannot tell which
    one it has, which is the point of the Protocol and is what the shared contract tests in
    `tests/test_storage.py` hold both of them to.

    ### Why this exists

    A managed runtime that scales to zero and replaces containers on every deploy has no disk
    worth writing a photograph to. `LocalObjectStore` on such a host is not *slower* or *less
    backed up* — it is wrong: the wardrobe rows outlive the images they point at, so the
    product shows a user broken pictures of their own clothes. This keeps the bytes where the
    rows already are, so the two cannot disagree about what exists.

    ### Blocking calls inside `async def`

    The same as `LocalObjectStore`, and tolerable for the same reason: it is the pattern the
    whole application already uses — every route handler opens a synchronous session inside
    an `async def` (see `app/routers/assets.py`). A single store that went async would not
    make the request async; it would only make this module disagree with every other one. If
    the event loop ever needs freeing, that change belongs at the session layer, once.
    """

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        validated_key(key)
        with self._sessions() as session:
            # `merge` rather than `add`: the key is derived from a freshly minted asset id,
            # so a collision means the same upload arriving twice, and the honest answer to
            # that is the newer bytes rather than an integrity error at the end of a retry.
            session.merge(
                AssetBlobRow(
                    storage_key=key,
                    content_type=content_type,
                    data=data,
                    byte_size=len(data),
                )
            )
            session.commit()
        logger.info("stored asset", extra={"bytes": len(data), "content_type": content_type})

    async def get(self, key: str) -> bytes:
        validated_key(key)
        with self._sessions() as session:
            row = session.get(AssetBlobRow, key)
            if row is None:
                raise StorageError("stored image could not be read")
            return row.data

    async def delete(self, key: str) -> None:
        validated_key(key)
        with self._sessions() as session:
            row = session.get(AssetBlobRow, key)
            if row is not None:
                session.delete(row)
                session.commit()

    async def exists(self, key: str) -> bool:
        validated_key(key)
        with self._sessions() as session:
            return session.get(AssetBlobRow, key) is not None


class InlineImageSource:
    """`ImageReferenceSource` that inlines a downscaled copy as a `data:` URL.

    The local default, and not a compromise: the provider needs the pixels either way, and
    inlining means there is no URL in existence afterwards to leak, log or expire wrongly.

    Downscaling here rather than in the caller is deliberate. The provider payload ceiling
    is a property of *sending an image to a provider*, which is exactly what this class is
    for; a 10 MB original inlined at full size is rejected by the provider, and the place
    that would have to remember to shrink it first is every future caller.

    `ttl_s` is accepted and ignored. Satisfying a Protocol that speaks in deadlines with
    something that has no lifetime at all is the strict direction, so it is silent rather
    than an error.
    """

    def __init__(self, store: ObjectStore, *, max_edge_px: int) -> None:
        self._store = store
        self._max_edge_px = max_edge_px

    async def provider_url(self, storage_key: str, *, ttl_s: int = 300) -> str:
        stored = await self._store.get(storage_key)
        downscaled = analysis_variant(stored, max_edge_px=self._max_edge_px)
        encoded = base64.b64encode(downscaled).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"


class SignedUrlImageSource:
    """`ImageReferenceSource` for a store that can issue its own signed URLs.

    Unused until S11, when the store is Supabase and the provider can reach it. Present now
    because its absence is what makes `InlineImageSource` look like the only option rather
    than the local one.
    """

    def __init__(self, signer: object) -> None:  # pragma: no cover - S11
        raise NotImplementedError(
            "signed provider URLs arrive with hosted object storage in S11; until then the "
            "storage directory is private and unreachable from the provider, so the image "
            "is inlined"
        )


#: The token's subject binds the owner to the asset. Split on this rather than parsed.
_SUBJECT_SEPARATOR = "/"


def image_subject(user_id: str, asset_id: str) -> str:
    return f"{user_id}{_SUBJECT_SEPARATOR}{asset_id}"


def split_image_subject(subject: str) -> tuple[str, str]:
    """The owner and asset a token was minted for. Raises `ValueError` if it is not both."""
    user_id, separator, asset_id = subject.partition(_SUBJECT_SEPARATOR)
    if not separator or not user_id or not asset_id:
        raise ValueError("image token subject is not owner/asset")
    return user_id, asset_id


def browser_image_url(
    asset_id: str, *, user_id: str, base_url: str, signer: TokenSigner, ttl_s: int
) -> str:
    """The `image_url` handed to the browser for one asset.

    Capability over identity: the token names one asset, expires, and is signed for the
    `image` purpose so it cannot be replayed as a session. Minted per read, so the lifetime
    can stay short without the wardrobe screen going blank while a user is looking at it.

    The **owner is inside the signed subject**, not just the asset. The route therefore
    still reads through the ownership-scoped query rather than fetching an asset by primary
    key — the token decides which scope to read in, and it cannot name a scope this API did
    not sign. Without it the asset route would be the one place in the application that
    loads an owned row without a `user_id`, which is exactly the bypass
    `tests/test_query_scoping.py` exists to forbid.

    The id is recoverable from the token by anyone holding it, which means the holder's own
    id in the holder's own URL. It is an opaque generated identifier, not a name or an
    email, and it never identifies a different user.
    """
    token = signer.mint(image_subject(user_id, asset_id), purpose=IMAGE_PURPOSE, ttl_s=ttl_s)
    return f"{base_url.rstrip('/')}/assets/{asset_id}/{token}"


__all__ = [
    "DatabaseObjectStore",
    "InlineImageSource",
    "LocalObjectStore",
    "ObjectStore",
    "SignedUrlImageSource",
    "StorageError",
    "browser_image_url",
    "extension_for",
    "image_subject",
    "split_image_subject",
    "storage_key",
    "validated_key",
]
