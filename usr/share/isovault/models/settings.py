"""
Settings management for the application.
Handles loading, saving and validation of user settings.
"""

import os
import configparser
from typing import Dict, Any, Optional
from config import APP_CONFIG, DEFAULT_S3_CONFIG, DEFAULT_WEB_CONFIG
from utils.i18n import _


class SettingsManager:
    """Manages application settings and S3 configuration"""
    
    def __init__(self):
        """Initialize settings manager with default values"""
        self.config_file = APP_CONFIG['config_file']
        self.settings = self._load_default_settings()
        self.load_settings()
    
    def _load_default_settings(self) -> Dict[str, Any]:
        """Load default settings"""
        return {
            'general': {
                'last_directory': None,
                'window_width': APP_CONFIG['window_width'],
                'window_height': APP_CONFIG['window_height'],
                'auto_refresh': True
            },
            's3': {
                'access_key': '',
                'secret_key': '',
                'endpoint_url': DEFAULT_S3_CONFIG['endpoint_url'],
                'region_name': DEFAULT_S3_CONFIG['region_name'],
                'bucket_name': DEFAULT_S3_CONFIG['bucket_name']
            },
            'web': {
                'base_url': DEFAULT_WEB_CONFIG['base_url'],
                'index_file': DEFAULT_WEB_CONFIG['index_file'],
                'show_index_files': False
            },
            'ui': {
                'show_progress_details': True,
                'confirm_deletions': True,
                'auto_update_index': True
            }
        }
    
    def load_settings(self) -> bool:
        """Load settings from config file"""
        try:
            if not os.path.exists(self.config_file):
                print(_("Config file not found: {config_file}").format(config_file=self.config_file))
                return False
            
            config = configparser.ConfigParser()
            config.read(self.config_file)
            
            # Load each section
            for section_name in self.settings.keys():
                if section_name in config:
                    for key, value in config[section_name].items():
                        # Handle boolean values
                        if isinstance(self.settings[section_name].get(key), bool):
                            self.settings[section_name][key] = config.getboolean(section_name, key)
                        # Handle integer values
                        elif isinstance(self.settings[section_name].get(key), int):
                            self.settings[section_name][key] = config.getint(section_name, key)
                        else:
                            self.settings[section_name][key] = value
            
            print(_("Settings loaded from: {config_file}").format(config_file=self.config_file))
            return True
            
        except Exception as e:
            print(_("Error loading settings: {error}").format(error=e))
            return False
    
    def save_settings(self) -> bool:
        """Save settings to config file"""
        try:
            # Create config directory if it doesn't exist
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            config = configparser.ConfigParser()
            
            # Convert settings to configparser format
            for section_name, section_data in self.settings.items():
                config[section_name] = {}
                for key, value in section_data.items():
                    if value is not None:
                        config[section_name][key] = str(value)
            
            with open(self.config_file, 'w') as f:
                config.write(f)
            
            print(_("Settings saved to: {config_file}").format(config_file=self.config_file))
            return True
            
        except Exception as e:
            print(_("Error saving settings: {error}").format(error=e))
            return False
    
    def get_s3_config(self) -> Dict[str, str]:
        """Get S3 configuration dictionary"""
        return {
            'access_key': self.get('s3', 'access_key'),
            'secret_key': self.get('s3', 'secret_key'),
            'endpoint_url': self.get('s3', 'endpoint_url'),
            'region_name': self.get('s3', 'region_name'),
            'bucket_name': self.get('s3', 'bucket_name')
        }
    
    def get_web_config(self) -> Dict[str, str]:
        """Get Web configuration dictionary"""
        return {
            'base_url': self.get('web', 'base_url'),
            'index_file': self.get('web', 'index_file'),
            'show_index_files': self.get('web', 'show_index_files', False)
        }
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a setting value"""
        return self.settings.get(section, {}).get(key, default)
    
    def set(self, section: str, key: str, value: Any) -> None:
        """Set a setting value"""
        if section not in self.settings:
            self.settings[section] = {}
        self.settings[section][key] = value
    
    def validate_s3_config(self) -> tuple[bool, str]:
        """Validate S3 configuration"""
        s3_config = self.get_s3_config()
        
        if not s3_config['access_key']:
            return False, _("Access key is required")
        
        if not s3_config['secret_key']:
            return False, _("Secret key is required")
        
        if not s3_config['endpoint_url']:
            return False, _("Endpoint URL is required")
        
        if not s3_config['bucket_name']:
            return False, _("Bucket name is required")
        
        return True, _("Configuration is valid")
    
    def has_s3_credentials(self) -> bool:
        """Check if S3 credentials are configured"""
        return bool(self.get('s3', 'access_key') and self.get('s3', 'secret_key'))
    
    def get_window_size(self) -> tuple[int, int]:
        """Get window size from settings"""
        width = self.get('general', 'window_width', APP_CONFIG['window_width'])
        height = self.get('general', 'window_height', APP_CONFIG['window_height'])
        return width, height
    
    def set_window_size(self, width: int, height: int) -> None:
        """Set window size in settings"""
        self.set('general', 'window_width', width)
        self.set('general', 'window_height', height)