def get_backup_catalog_image_url() -> str:
    from adk_common.utils.constants import get_required_env_var
    return get_required_env_var("BACKUP_CATALOG_IMAGE_URL")


def get_backup_logo_url() -> str:
    from adk_common.utils.constants import get_required_env_var
    return get_required_env_var("BACKUP_LOGO_IMAGE_URL")