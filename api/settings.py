from fastapi import APIRouter
from ..schemas import Settings
from ..config import load_config, save_config

router = APIRouter()

@router.get("/", response_model=SuccessResponse)
async def get_settings():
    """获取当前设置"""
    config = load_config()
    settings = Settings(
        general=GeneralSettings(**config.get('general', {})),
        asset_search=AssetSearchSettings(**config.get('asset_search', {}))
    )
    return SuccessResponse(success=True, message="获取设置成功", data=settings)

@router.post("/", response_model=SuccessResponse)
async def update_settings(settings: Settings):
    """更新设置"""
    config = load_config()
    config['general'] = settings.general.dict()
    config['asset_search'] = settings.asset_search.dict()
    save_config(config)
    return SuccessResponse(success=True, message="设置已保存")
