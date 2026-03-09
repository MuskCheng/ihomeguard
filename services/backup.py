"""备份与恢复服务"""
import json
from datetime import datetime
from typing import Dict, List, Tuple


BACKUP_VERSION = "1.0"


def export_backup(include_devices: bool = False, include_alerts: bool = False) -> Dict:
    """导出备份
    
    Args:
        include_devices: 是否包含设备别名/信任信息
        include_alerts: 是否包含未处理告警
    
    Returns:
        备份数据字典
    """
    import config
    import storage
    
    backup_data = {
        "version": BACKUP_VERSION,
        "export_time": datetime.now().isoformat(),
        "app_version": config.get_version(),
        "config": _export_config(),
    }
    
    if include_devices:
        backup_data["devices"] = _export_devices()
    
    if include_alerts:
        backup_data["alerts"] = _export_alerts()
    
    return backup_data


def _export_config() -> Dict:
    """导出配置（去除敏感信息的明文）"""
    import config
    
    cfg = config.get_config()
    
    return {
        "ikuai": {
            "local_url": cfg["ikuai"].get("local_url", ""),
            "username": cfg["ikuai"].get("username", ""),
            # 密码不导出，需要用户重新输入
        },
        "pushme": {
            "push_key": cfg["pushme"].get("push_key", ""),
            "wecom_webhook": cfg["pushme"].get("wecom_webhook", ""),
            "dingtalk_webhook": cfg["pushme"].get("dingtalk_webhook", ""),
            "dingtalk_secret": cfg["pushme"].get("dingtalk_secret", ""),
            "enabled": cfg["pushme"].get("enabled", True),
        },
        "monitor": cfg.get("monitor", {}),
        "web": cfg.get("web", {}),
    }


def _export_devices() -> List[Dict]:
    """导出设备别名和信任信息"""
    import storage
    
    devices = storage.get_all_devices()
    
    # 只导出用户设置的字段
    return [
        {
            "mac": d["mac"],
            "alias": d.get("alias", ""),
            "is_trusted": d.get("is_trusted", 0),
        }
        for d in devices
        if d.get("alias") or d.get("is_trusted")  # 只导出有设置的设备
    ]


def _export_alerts() -> List[Dict]:
    """导出未处理告警"""
    import storage
    
    alerts = storage.get_unresolved_alerts()
    
    return [
        {
            "alert_type": a["alert_type"],
            "severity": a.get("severity", "info"),
            "mac": a.get("mac", ""),
            "message": a.get("message", ""),
            "created_at": a.get("created_at", ""),
        }
        for a in alerts
    ]


def import_backup(backup_data: Dict, merge_devices: bool = True) -> Tuple[bool, str, Dict]:
    """导入备份
    
    Args:
        backup_data: 备份数据
        merge_devices: 是否合并设备（True=合并，False=覆盖）
    
    Returns:
        (success, message, stats)
    """
    import config
    import storage
    
    # 验证格式
    if not isinstance(backup_data, dict):
        return False, "无效的备份文件格式", {}
    
    if "version" not in backup_data:
        return False, "缺少版本信息", {}
    
    if "config" not in backup_data:
        return False, "缺少配置数据", {}
    
    stats = {
        "config_updated": False,
        "devices_imported": 0,
        "alerts_imported": 0,
    }
    
    try:
        # 导入配置
        if "config" in backup_data:
            _import_config(backup_data["config"])
            stats["config_updated"] = True
        
        # 导入设备
        if "devices" in backup_data:
            count = _import_devices(backup_data["devices"], merge_devices)
            stats["devices_imported"] = count
        
        # 导入告警
        if "alerts" in backup_data:
            count = _import_alerts(backup_data["alerts"])
            stats["alerts_imported"] = count
        
        return True, "导入成功", stats
    
    except Exception as e:
        return False, f"导入失败: {str(e)}", stats


def _import_config(config_data: Dict):
    """导入配置"""
    import config
    
    cfg = config.get_config()
    
    # 更新爱快配置（不更新密码）
    if "ikuai" in config_data:
        ikuai_data = config_data["ikuai"]
        if ikuai_data.get("local_url"):
            cfg["ikuai"]["local_url"] = ikuai_data["local_url"]
        if ikuai_data.get("username"):
            cfg["ikuai"]["username"] = ikuai_data["username"]
        # 密码保留原值
    
    # 更新推送配置
    if "pushme" in config_data:
        pushme_data = config_data["pushme"]
        for key in ["push_key", "wecom_webhook", "dingtalk_webhook", "dingtalk_secret", "enabled"]:
            if key in pushme_data:
                cfg["pushme"][key] = pushme_data[key]
    
    # 更新监控配置
    if "monitor" in config_data:
        cfg["monitor"].update(config_data["monitor"])
    
    # 更新 Web 配置
    if "web" in config_data:
        cfg["web"].update(config_data["web"])
    
    config.save_config(cfg)


def _import_devices(devices: List[Dict], merge: bool = True) -> int:
    """导入设备信息
    
    Args:
        devices: 设备列表
        merge: True=合并（只更新本地没有的数据），False=覆盖
    
    Returns:
        导入数量
    """
    import storage
    
    count = 0
    for device in devices:
        mac = device.get("mac", "").upper()
        if not mac:
            continue
        
        alias = device.get("alias", "")
        is_trusted = device.get("is_trusted", 0)
        
        # 检查设备是否存在
        existing = storage.get_device(mac)
        
        if existing:
            if merge:
                # 合并模式：只更新空值
                if not existing.get("alias") and alias:
                    storage.update_device_alias(mac, alias, is_trusted)
                    count += 1
                elif alias and existing.get("alias") != alias:
                    # 如果备份中有别名，更新（备份优先）
                    storage.update_device_alias(mac, alias, is_trusted)
                    count += 1
            else:
                # 覆盖模式
                storage.update_device_alias(mac, alias, is_trusted)
                count += 1
        else:
            # 设备不存在，先创建再更新
            storage.upsert_device(mac)
            if alias or is_trusted:
                storage.update_device_alias(mac, alias, is_trusted)
                count += 1
    
    return count


def _import_alerts(alerts: List[Dict]) -> int:
    """导入告警
    
    Returns:
        导入数量
    """
    import storage
    
    count = 0
    for alert in alerts:
        try:
            storage.add_alert(
                alert_type=alert.get("alert_type", "unknown"),
                severity=alert.get("severity", "info"),
                mac=alert.get("mac", ""),
                message=alert.get("message", ""),
            )
            count += 1
        except Exception:
            pass
    
    return count


def get_backup_stats() -> Dict:
    """获取备份统计信息"""
    import storage
    
    devices = storage.get_all_devices()
    alerts = storage.get_unresolved_alerts()
    
    # 统计有设置的设备
    devices_with_settings = sum(1 for d in devices if d.get("alias") or d.get("is_trusted"))
    
    return {
        "devices_total": len(devices),
        "devices_with_settings": devices_with_settings,
        "unresolved_alerts": len(alerts),
    }
