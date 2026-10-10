"""
Regenerates and uploads the public index pages.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

from config import INDEX_FILE, ROOT_FOLDER
from services.html_generator import IndexGenerator
from services.s3_service import S3Service, object_key

logger = logging.getLogger(__name__)

_MAX_PARALLEL_READS = 8


def publish_indexes(s3_service: S3Service, generator: IndexGenerator) -> List[str]:
    """
    Upload the main index and one index per folder of the profile
    (the folders come from the generator).

    The bucket is listed once and the checksum files are read in parallel.
    Folder pages are always rewritten, so a folder that became empty doesn't
    keep showing deleted ISOs.

    Returns:
        Keys of the uploaded index files
    """
    files = s3_service.list_files()
    md5_hashes = _read_checksums(s3_service, files)

    uploaded = []
    s3_service.upload_text(generator.generate_main_index(files, md5_hashes), INDEX_FILE, "text/html")
    uploaded.append(INDEX_FILE)

    for folder in generator.folders:
        if folder == ROOT_FOLDER:  # the main index already is the root page
            continue
        folder_files = [f for f in files if f["folder"] == folder]
        key = object_key(folder, INDEX_FILE)
        s3_service.upload_text(
            generator.generate_folder_index(folder, folder_files, md5_hashes), key, "text/html"
        )
        uploaded.append(key)

    logger.info("Published %d index files", len(uploaded))
    return uploaded


def _read_checksums(s3_service: S3Service, files: List[Dict]) -> Dict[str, str]:
    """Checksum file key -> file content. Unreadable files are skipped."""
    keys = [f["key"] for f in files if f["name"].lower().endswith(".md5")]

    def read(key: str):
        try:
            return key, s3_service.read_text(key)
        except Exception as e:  # one bad checksum file must not block publishing
            logger.warning("Could not read %s: %s", key, e)
            return key, ""

    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL_READS) as pool:
        return dict(pool.map(read, keys))
