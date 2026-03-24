"""
HTML generation service for creating index pages.
"""

import html
import re
from typing import List, Dict, Optional
from datetime import datetime
from config import DISTRO_FOLDERS
from utils.i18n import _


class HTMLGenerator:
    """Generates HTML content for web index pages"""
    
    def __init__(self, s3_service=None):
        """
        Initialize HTML generator.
        
        Args:
            s3_service: S3Service instance for file operations
        """
        self.s3_service = s3_service
    
    def generate_main_index(self, all_files: List[Dict]) -> str:
        """
        Generate main index.html with file listing.
        
        Args:
            all_files: List of all file dictionaries
            
        Returns:
            HTML content as string
        """
        # Group files by folder and pair ISOs with MD5s
        folders = {}
        for file_info in all_files:
            folder = file_info['folder']
            if folder not in folders:
                folders[folder] = []
            folders[folder].append(file_info)
        
        # Only include folders that have files
        sorted_folders = []
        for folder in ['Root', 'Gnome', 'Cinnamon', 'XFCE']:
            if folder in folders and folders[folder]:
                grouped_files = self._group_files_with_md5(folders[folder])
                # Only add if there are ISO files (not just orphaned MD5s)
                if any(group['iso'] for group in grouped_files):
                    sorted_folders.append((folder, grouped_files))
        
        # Generate HTML
        html = self._generate_html_header(_("BigCommunity ISO Repository"))
        html += self._generate_main_body(sorted_folders)
        html += self._generate_html_footer()
        
        return html
    
    def generate_folder_index(self, folder_name: str, files: List[Dict]) -> str:
        """
        Generate index.html for a specific folder.
        
        Args:
            folder_name: Name of the folder
            files: List of file dictionaries in the folder
            
        Returns:
            HTML content as string
        """
        grouped_files = self._group_files_with_md5(files)
        
        html = self._generate_html_header(_("{folder_name} - BigCommunity ISO Repository").format(folder_name=folder_name))
        html += self._generate_folder_body(folder_name, grouped_files)
        html += self._generate_html_footer()
        
        return html
    
    def _generate_html_header(self, title: str) -> str:
        """Generate HTML header with CSS"""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }}
        
        .header {{
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 2rem 0;
            text-align: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.2);
            margin-bottom: 2rem;
        }}
        
        .logo {{
            font-size: 3rem;
            font-weight: bold;
            background: linear-gradient(45deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 0.5rem;
        }}
        
        .subtitle {{
            color: #666;
            font-size: 1.2rem;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 2rem;
        }}
        
        .folder-section {{
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 2rem;
            margin-bottom: 2rem;
            backdrop-filter: blur(10px);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        }}
        
        .folder-header {{
            display: flex;
            align-items: center;
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 2px solid #f0f0f0;
        }}
        
        .folder-icon {{
            width: 2.5rem;
            height: 2.5rem;
            margin-right: 1rem;
            fill: #495057;
        }}
        
        .folder-name {{
            font-size: 1.8rem;
            font-weight: bold;
            color: #333;
        }}
        
        .file-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(600px, 1fr));
            gap: 2rem;
        }}
        
        .file-card {{
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 12px;
            padding: 2.5rem;
            transition: all 0.3s ease;
            cursor: pointer;
            min-height: 200px;
        }}
        
        .file-card:hover {{
            background: #e9ecef;
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
        }}
        
        .file-name {{
            font-weight: 600;
            color: #495057;
            margin-bottom: 1rem;
            word-break: break-word;
            font-size: 1.1rem;
            line-height: 1.3;
        }}
        
        .file-info {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.9rem;
            color: #6c757d;
            margin-bottom: 1.5rem;
        }}
        
        .file-size {{
            font-weight: 600;
            color: #495057;
        }}
        
        .file-date {{
            font-size: 0.85rem;
        }}
        
        .md5-container {{
            margin-bottom: 1.5rem;
        }}
        
        .md5-label {{
            font-size: 0.75rem;
            color: #80868b;
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 500;
        }}
        
        .md5-hash {{
            background: #f1f3f4;
            border: 1px solid #dadce0;
            border-radius: 6px;
            padding: 0.75rem;
            font-family: 'Courier New', monospace;
            font-size: 0.85rem;
            color: #5f6368;
            word-break: break-all;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        
        .md5-hash:hover {{
            background: #e8eaed;
            border-color: #c1c7cd;
        }}
        
        .download-btn {{
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 500;
            transition: all 0.3s ease;
            width: 100%;
        }}
        
        .download-btn:hover {{
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
        }}
        
        .stats {{
            background: rgba(255, 255, 255, 0.9);
            border-radius: 10px;
            padding: 1rem;
            margin-bottom: 2rem;
            text-align: center;
        }}
        
        .empty-folder {{
            text-align: center;
            color: #6c757d;
            font-style: italic;
            padding: 3rem;
        }}
        
        .breadcrumb {{
            background: rgba(255, 255, 255, 0.9);
            border-radius: 10px;
            padding: 1rem;
            margin-bottom: 2rem;
        }}
        
        .breadcrumb a {{
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
        }}
        
        .breadcrumb a:hover {{
            text-decoration: underline;
        }}
        
        .footer {{
            text-align: center;
            padding: 2rem;
            color: rgba(255, 255, 255, 0.8);
            margin-top: 3rem;
        }}
        
        @media (max-width: 768px) {{
            .file-grid {{
                grid-template-columns: 1fr;
            }}
            
            .container {{
                padding: 0 1rem;
            }}
            
            .logo {{
                font-size: 2rem;
            }}
            
            .file-card {{
                padding: 1.5rem;
            }}
        }}
    </style>
</head>
<body>"""
    
    def _generate_main_body(self, sorted_folders: List) -> str:
        """Generate main page body content"""
        total_isos = len([f for folder_files in [folder[1] for folder in sorted_folders] 
                         for f in folder_files if f['iso']])
        
        body = f"""
    <div class="header">
        <div class="container">
            <h1 class="logo">BigCommunity</h1>
            <p class="subtitle">{_("Linux Distribution ISO Repository")}</p>
        </div>
    </div>
    
    <div class="container">
        <div class="stats">
            <strong>{_("{total_isos} ISO files available").format(total_isos=total_isos)}</strong> | {_("Updated")}: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
        </div>
"""
        
        # Add search functionality
        body += f"""
        <div class="stats">
            <input type="text" id="searchInput" placeholder="{_("Search ISOs...")}" style="
                width: 100%;
                max-width: 400px;
                padding: 1rem;
                border: none;
                border-radius: 25px;
                background: rgba(255,255,255,0.9);
                font-size: 1rem;
                outline: none;
            ">
        </div>
"""
        
        if not sorted_folders:
            body += f'''
        <div class="folder-section">
            <div class="empty-folder">{_("No ISO files available yet")}</div>
        </div>
'''
        else:
            # Generate sections for each folder
            for folder_name, folder_files in sorted_folders:
                folder_icon_svg = self._get_folder_icon_svg(folder_name)
                
                body += f"""
        <div class="folder-section">
            <div class="folder-header">
                {folder_icon_svg}
                <h2 class="folder-name">{folder_name}</h2>
            </div>
            <div class="file-grid">
"""
                
                for file_group in sorted(folder_files, key=lambda x: x['iso']['name'] if x['iso'] else ''):
                    if file_group['iso']:
                        body += self._generate_file_card(file_group)
                
                body += '            </div>\n        </div>\n'
        
        body += '    </div>\n'
        return body
    
    def _generate_folder_body(self, folder_name: str, grouped_files: List) -> str:
        """Generate folder page body content"""
        folder_icon_svg = self._get_folder_icon_svg(folder_name)
        
        body = f"""
    <div class="header">
        <div class="container">
            <h1 class="logo">BigCommunity</h1>
            <p class="subtitle">{_("Linux Distribution ISO Repository")}</p>
        </div>
    </div>
    
    <div class="container">
        <div class="breadcrumb">
            <a href="../">{_("← Back to All Folders")}</a> / <strong>{folder_name}</strong>
        </div>
        
        <div class="folder-section">
            <div class="folder-header">
                {folder_icon_svg}
                <h2 class="folder-name">{folder_name}</h2>
            </div>
"""
        
        if grouped_files:
            body += '            <div class="file-grid">\n'
            
            for file_group in sorted(grouped_files, key=lambda x: x['iso']['name'] if x['iso'] else x['md5']['name']):
                if file_group['iso']:
                    body += self._generate_file_card(file_group)
            
            body += '            </div>\n'
        else:
            body += f'            <div class="empty-folder">{_("No files in this folder")}</div>\n'
        
        body += '        </div>\n    </div>\n'
        return body
    
    def _generate_file_card(self, file_group: Dict) -> str:
        """Generate HTML for a single file card"""
        iso_info = file_group['iso']
        md5_info = file_group.get('md5')
        
        if not iso_info:
            return ""
        
        file_url = self._get_public_url(iso_info['key'])
        file_date = iso_info['modified'].strftime('%Y-%m-%d')

        # Escape all user-controlled values to prevent XSS
        safe_name = html.escape(iso_info["name"])
        safe_url = html.escape(file_url, quote=True)
        safe_date = html.escape(file_date)
        safe_size = html.escape(iso_info["size_formatted"])

        card = f"""
                <div class="file-card" onclick="window.open('{safe_url}', '_blank')">
                    <div class="file-name">{safe_name}</div>
                    <div class="file-info">
                        <span class="file-size">{safe_size}</span>
                        <span class="file-date">{safe_date}</span>
                    </div>
"""
        
        # Add MD5 hash if available
        if md5_info:
            md5_hash = self._read_md5_content(md5_info['key'])
            # Validate MD5 is a proper hex string to prevent injection
            if re.fullmatch(r"[a-fA-F0-9]{32}", md5_hash):
                safe_md5 = md5_hash.lower()
            else:
                safe_md5 = html.escape(md5_hash)
            card += f"""
                    <div class="md5-container">
                        <div class="md5-label">{html.escape(_("MD5 Checksum"))}</div>
                        <div class="md5-hash" onclick="event.stopPropagation(); navigator.clipboard.writeText('{safe_md5}'); this.style.background='#d4edda';">
                            {safe_md5}
                        </div>
                    </div>
"""
        
        card += f"""
                    <button class="download-btn" onclick="event.stopPropagation(); window.open('{safe_url}', '_blank')">
                        {html.escape(_("Download ISO"))}
                    </button>
                </div>
"""
        
        return card
    
    def _generate_html_footer(self) -> str:
        """Generate HTML footer with JavaScript"""
        return f"""
    <div class="footer">
        <p>{_("Generated by ISOVault")} | <a href="https://communitybig.org" style="color: rgba(255,255,255,0.9);">communitybig.org</a></p>
    </div>
    
    <script>
        // Add interactivity
        document.addEventListener('DOMContentLoaded', function() {{
            // Add loading animation for downloads
            document.querySelectorAll('.download-btn').forEach(btn => {{
                btn.addEventListener('click', function() {{
                    this.innerHTML = '{_("Downloading...")}';
                    setTimeout(() => {{
                        this.innerHTML = '{_("Download ISO")}';
                    }}, 2000);
                }});
            }});
            
            // Search functionality
            const searchInput = document.getElementById('searchInput');
            if (searchInput) {{
                searchInput.addEventListener('input', function() {{
                    const searchTerm = this.value.toLowerCase();
                    document.querySelectorAll('.file-card').forEach(card => {{
                        const fileName = card.querySelector('.file-name').textContent.toLowerCase();
                        card.style.display = fileName.includes(searchTerm) ? 'block' : 'none';
                    }});
                }});
            }}
            
            // Copy MD5 feedback
            document.querySelectorAll('.md5-hash').forEach(hash => {{
                hash.addEventListener('click', function() {{
                    const originalBg = this.style.background;
                    this.style.background = '#d4edda';
                    setTimeout(() => {{
                        this.style.background = originalBg;
                    }}, 2000);
                }});
            }});
        }});
    </script>
</body>
</html>"""
    
    def _get_folder_icon_svg(self, folder_name: str) -> str:
        """Get SVG icon for folder"""
        icons = {
            'Root': '''<svg class="folder-icon" viewBox="0 0 24 24"><path d="M3 9L12 2L21 9V20C21 20.5304 20.7893 21.0391 20.4142 21.4142C20.0391 21.7893 19.5304 22 19 22H5C4.46957 22 3.96086 21.7893 3.58579 21.4142C3.21071 21.0391 3 20.5304 3 20V9Z"/><polyline points="9,22 9,12 15,12 15,22"/></svg>''',
            'Gnome': '''<svg class="folder-icon" viewBox="0 0 24 24"><path d="M12 2C13.1 2 14 2.9 14 4C14 5.1 13.1 6 12 6C10.9 6 10 5.1 10 4C10 2.9 10.9 2 12 2Z"/><path d="M21 9V7L15 1L9 7V9C9 10.1 9.9 11 11 11V20C11 21.1 11.9 22 13 22S15 21.1 15 20V11C16.1 11 17 10.1 17 9Z"/></svg>''',
            'Cinnamon': '''<svg class="folder-icon" viewBox="0 0 24 24"><path d="M12 2L2 7L12 12L22 7L12 2Z"/><polyline points="2,17 12,22 22,17"/><polyline points="2,12 12,17 22,12"/></svg>''',
            'XFCE': '''<svg class="folder-icon" viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>'''
        }
        return icons.get(folder_name, icons['Root'])
    
    def _group_files_with_md5(self, files: List[Dict]) -> List[Dict]:
        """Group ISO files with their corresponding MD5 files"""
        iso_files = [f for f in files if f['name'].lower().endswith('.iso')]
        md5_files = [f for f in files if f['name'].lower().endswith('.md5')]
        
        grouped = []
        
        for iso_file in iso_files:
            iso_base = iso_file['name'].lower().replace('.iso', '')
            md5_match = None
            
            # Find corresponding MD5 file
            for md5_file in md5_files:
                md5_base = md5_file['name'].lower().replace('.md5', '').replace('.iso.md5', '')
                if iso_base == md5_base or md5_base in iso_base:
                    md5_match = md5_file
                    break
            
            grouped.append({
                'iso': iso_file,
                'md5': md5_match
            })
        
        # Add orphaned MD5 files (without corresponding ISO)
        used_md5_files = [g['md5'] for g in grouped if g['md5']]
        for md5_file in md5_files:
            if md5_file not in used_md5_files:
                grouped.append({
                    'iso': None,
                    'md5': md5_file
                })
        
        return grouped
    
    def _get_public_url(self, file_key: str) -> str:
        """Generate public URL for a file"""
        if file_key.startswith('/'):
            file_key = file_key[1:]  # Remove leading slash
        
        # Use S3 service to get public URL if available
        if self.s3_service:
            return self.s3_service.get_public_url(file_key)
        
        # Fallback
        return f"/{file_key}"
    
    def _read_md5_content(self, md5_key: str) -> str:
        """Read MD5 hash from file or extract from filename"""
        try:
            # Try to read actual MD5 file content if S3 service is available
            if self.s3_service:
                content = self.s3_service.read_file_content(md5_key)
                if content:
                    # MD5 files usually contain just the hash and filename
                    # Extract the 32-character hash
                    md5_pattern = r'[a-fA-F0-9]{32}'
                    match = re.search(md5_pattern, content)
                    if match:
                        return match.group().lower()
            
            # Fallback: extract from filename
            filename = md5_key.split('/')[-1]  # Get just the filename
            return self._extract_md5_from_filename(filename)
            
        except Exception as e:
            print(f"Error reading MD5 content: {e}")
            # Final fallback: use filename
            filename = md5_key.split('/')[-1]
            return self._extract_md5_from_filename(filename)
    
    def _extract_md5_from_filename(self, filename: str) -> str:
        """Extract MD5 hash from filename"""
        try:
            # Remove extension
            base_name = filename.replace('.md5', '').replace('.MD5', '')
            
            # If it's just a 32-character hash
            if len(base_name) == 32 and all(c in '0123456789abcdefABCDEF' for c in base_name):
                return base_name.lower()

            # Try to extract hash from complex filenames
            md5_pattern = r'[a-fA-F0-9]{32}'
            match = re.search(md5_pattern, filename)
            if match:
                return match.group().lower()
            
            # Fallback: return filename without extension
            return base_name
            
        except Exception as e:
            print(_("Error extracting MD5 from {filename}: {error}").format(filename=filename, error=e))
            return filename