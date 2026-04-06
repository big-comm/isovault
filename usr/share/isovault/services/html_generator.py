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

    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">

    <!-- Lucide Icons -->
    <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>

    <style>
        :root {{
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-tertiary: #1a1a25;
            --bg-card: rgba(25, 25, 35, 0.7);
            --bg-glass: rgba(255, 255, 255, 0.03);
            --bg-glass-strong: rgba(255, 255, 255, 0.08);
            --text-primary: #f5f5f7;
            --text-secondary: #a1a1a6;
            --text-muted: #6e6e73;
            --accent-blue: #0a84ff;
            --accent-purple: #bf5af2;
            --accent-green: #30d158;
            --accent-orange: #ff9f0a;
            --accent-pink: #ff375f;
            --gradient-hero: linear-gradient(135deg, #0a0a1a 0%, #1a1a3e 25%, #0f0f2d 50%, #151530 75%, #0a0a1a 100%);
            --gradient-accent: linear-gradient(135deg, var(--accent-blue) 0%, var(--accent-purple) 50%, var(--accent-pink) 100%);
            --border-subtle: rgba(255, 255, 255, 0.08);
            --border-light: rgba(255, 255, 255, 0.12);
            --shadow-lg: 0 16px 48px rgba(0, 0, 0, 0.5);
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
            --radius-xl: 24px;
            --radius-full: 9999px;
            --transition-base: 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            --transition-fast: 0.15s ease;
            --font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }}

        *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
        html {{ scroll-behavior: smooth; }}

        body {{
            font-family: var(--font-family);
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
        }}

        .header {{
            background: rgba(10, 10, 15, 0.85);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--border-subtle);
            padding: 1rem 0;
            position: sticky;
            top: 0;
            z-index: 200;
        }}

        .header .container {{
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .logo {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            text-decoration: none;
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--text-primary);
        }}

        .text-gradient {{
            background: var(--gradient-accent);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .header-nav {{
            display: flex;
            align-items: center;
            gap: 1.5rem;
        }}

        .header-nav a {{
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 0.875rem;
            font-weight: 500;
            transition: color var(--transition-fast);
        }}

        .header-nav a:hover {{ color: var(--text-primary); }}

        .hero {{
            background: var(--gradient-hero);
            padding: 5rem 0 3rem;
            text-align: center;
            position: relative;
            overflow: hidden;
        }}

        .hero::before {{
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 600px;
            height: 600px;
            background: radial-gradient(ellipse, rgba(10, 132, 255, 0.12) 0%, transparent 70%);
            pointer-events: none;
        }}

        .hero h1 {{
            font-size: 3rem;
            font-weight: 800;
            margin-bottom: 0.75rem;
            position: relative;
        }}

        .hero p {{
            color: var(--text-secondary);
            font-size: 1.125rem;
            max-width: 600px;
            margin: 0 auto;
            position: relative;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 2rem;
        }}

        .stats-bar {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 2rem;
            padding: 1rem 1.5rem;
            background: var(--bg-card);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-lg);
            margin: -1.5rem auto 2.5rem;
            max-width: 700px;
            position: relative;
            z-index: 10;
        }}

        .stats-bar .stat {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.875rem;
            color: var(--text-secondary);
        }}

        .stats-bar .stat strong {{ color: var(--text-primary); }}
        .stats-bar .stat i {{ color: var(--accent-blue); width: 16px; height: 16px; }}
        .stat-divider {{ width: 1px; height: 20px; background: var(--border-light); }}

        .search-wrapper {{
            max-width: 500px;
            margin: 0 auto 2.5rem;
            position: relative;
        }}

        .search-wrapper i {{
            position: absolute;
            left: 1rem;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            width: 18px;
            height: 18px;
            pointer-events: none;
        }}

        .search-input {{
            width: 100%;
            padding: 0.875rem 1rem 0.875rem 2.75rem;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-full);
            color: var(--text-primary);
            font-family: var(--font-family);
            font-size: 0.9375rem;
            outline: none;
            transition: var(--transition-base);
            backdrop-filter: blur(20px);
        }}

        .search-input::placeholder {{ color: var(--text-muted); }}

        .search-input:focus {{
            border-color: var(--accent-blue);
            box-shadow: 0 0 0 3px rgba(10, 132, 255, 0.15);
        }}

        .de-section {{ margin-bottom: 2.5rem; }}

        .de-header {{
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border-subtle);
        }}

        .de-badge {{
            display: flex;
            align-items: center;
            justify-content: center;
            width: 48px;
            height: 48px;
            border-radius: var(--radius-md);
            font-size: 1.25rem;
        }}

        .de-badge i {{ width: 24px; height: 24px; }}

        .de-badge.gnome {{
            background: linear-gradient(135deg, rgba(108, 92, 231, 0.2), rgba(108, 92, 231, 0.05));
            color: #6c5ce7;
            border: 1px solid rgba(108, 92, 231, 0.3);
        }}

        .de-badge.xfce {{
            background: linear-gradient(135deg, rgba(46, 134, 222, 0.2), rgba(46, 134, 222, 0.05));
            color: #2e86de;
            border: 1px solid rgba(46, 134, 222, 0.3);
        }}

        .de-badge.cinnamon {{
            background: linear-gradient(135deg, rgba(211, 84, 0, 0.2), rgba(211, 84, 0, 0.05));
            color: #d35400;
            border: 1px solid rgba(211, 84, 0, 0.3);
        }}

        .de-badge.root {{
            background: linear-gradient(135deg, rgba(10, 132, 255, 0.2), rgba(10, 132, 255, 0.05));
            color: var(--accent-blue);
            border: 1px solid rgba(10, 132, 255, 0.3);
        }}

        .de-info h2 {{ font-size: 1.5rem; font-weight: 700; }}
        .de-info .de-count {{ font-size: 0.8125rem; color: var(--text-muted); font-weight: 400; }}

        .file-grid {{
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 1.25rem;
        }}

        .file-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-xl);
            padding: 1.75rem;
            backdrop-filter: blur(20px);
            transition: var(--transition-base);
            display: flex;
            flex-direction: column;
            width: 100%;
            max-width: 420px;
            min-width: 300px;
            flex: 1 1 340px;
        }}

        .file-card:hover {{
            transform: translateY(-3px);
            box-shadow: var(--shadow-lg);
            border-color: var(--border-light);
        }}

        .file-card-header {{
            display: flex;
            align-items: flex-start;
            gap: 0.75rem;
            margin-bottom: 1rem;
        }}

        .file-icon {{
            display: flex;
            align-items: center;
            justify-content: center;
            width: 40px;
            height: 40px;
            border-radius: var(--radius-sm);
            background: var(--bg-glass-strong);
            flex-shrink: 0;
        }}

        .file-icon i {{ color: var(--accent-blue); width: 20px; height: 20px; }}

        .file-name {{
            font-weight: 600;
            font-size: 0.9375rem;
            color: var(--text-primary);
            line-height: 1.4;
            word-break: break-word;
        }}

        .file-meta {{
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1rem;
            flex-wrap: wrap;
        }}

        .file-meta-item {{
            display: flex;
            align-items: center;
            gap: 0.375rem;
            font-size: 0.8125rem;
            color: var(--text-secondary);
        }}

        .file-meta-item i {{ width: 14px; height: 14px; }}
        .file-meta-item.size {{ color: var(--accent-green); font-weight: 600; }}
        .file-meta-item.date i {{ color: var(--text-muted); }}

        .md5-section {{ margin-bottom: 1.25rem; }}

        .md5-label {{
            font-size: 0.6875rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
            margin-bottom: 0.375rem;
        }}

        .md5-row {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-sm);
            padding: 0.625rem 0.75rem;
            transition: var(--transition-fast);
        }}

        .md5-row:hover {{ border-color: var(--border-light); }}

        .md5-hash {{
            font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
            font-size: 0.75rem;
            color: var(--text-muted);
            word-break: break-all;
            flex: 1;
            user-select: all;
        }}

        .md5-copy-btn {{
            background: none;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            padding: 4px;
            border-radius: 4px;
            transition: var(--transition-fast);
            display: flex;
            align-items: center;
            flex-shrink: 0;
        }}

        .md5-copy-btn:hover {{ color: var(--accent-blue); background: var(--bg-glass-strong); }}
        .md5-copy-btn i {{ width: 14px; height: 14px; }}

        .download-btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            padding: 0.75rem 1.25rem;
            background: var(--gradient-accent);
            color: white;
            border: none;
            border-radius: var(--radius-md);
            font-family: var(--font-family);
            font-size: 0.875rem;
            font-weight: 600;
            cursor: pointer;
            transition: var(--transition-base);
            text-decoration: none;
            margin-top: auto;
            width: 100%;
        }}

        .download-btn:hover {{
            transform: translateY(-1px);
            box-shadow: 0 6px 24px rgba(10, 132, 255, 0.35);
        }}

        .download-btn i {{ width: 18px; height: 18px; }}

        .empty-state {{
            text-align: center;
            padding: 4rem 2rem;
            color: var(--text-muted);
        }}

        .empty-state i {{ width: 48px; height: 48px; margin-bottom: 1rem; opacity: 0.3; }}

        .breadcrumb {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 1rem 1.5rem;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-lg);
            margin-bottom: 2rem;
            backdrop-filter: blur(20px);
        }}

        .breadcrumb a {{
            color: var(--accent-blue);
            text-decoration: none;
            font-weight: 500;
            font-size: 0.875rem;
            transition: color var(--transition-fast);
        }}

        .breadcrumb a:hover {{ color: var(--text-primary); }}
        .breadcrumb span {{ color: var(--text-muted); font-size: 0.875rem; }}
        .breadcrumb strong {{ font-size: 0.875rem; }}

        .footer {{
            text-align: center;
            padding: 3rem 2rem;
            margin-top: 2rem;
            border-top: 1px solid var(--border-subtle);
        }}

        .footer p {{ color: var(--text-muted); font-size: 0.8125rem; }}

        .footer a {{
            color: var(--accent-blue);
            text-decoration: none;
            transition: color var(--transition-fast);
        }}

        .footer a:hover {{ color: var(--text-primary); }}

        .toast {{
            position: fixed;
            bottom: 2rem;
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: var(--bg-tertiary);
            border: 1px solid var(--border-light);
            color: var(--text-primary);
            padding: 0.75rem 1.5rem;
            border-radius: var(--radius-full);
            font-size: 0.875rem;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            box-shadow: var(--shadow-lg);
            transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
            z-index: 999;
            pointer-events: none;
        }}

        .toast.show {{ transform: translateX(-50%) translateY(0); }}
        .toast i {{ width: 16px; height: 16px; color: var(--accent-green); }}

        @media (max-width: 768px) {{
            .container {{ padding: 0 1rem; }}
            .hero {{ padding: 3.5rem 0 2rem; }}
            .hero h1 {{ font-size: 2rem; }}
            .hero p {{ font-size: 1rem; }}
            .stats-bar {{ flex-direction: column; gap: 0.75rem; margin: -1rem 1rem 2rem; }}
            .stat-divider {{ display: none; }}
            .file-grid {{ flex-direction: column; align-items: center; }}
            .file-card {{ padding: 1.25rem; max-width: 100%; min-width: 0; flex: 1 1 auto; }}
            .de-badge {{ width: 40px; height: 40px; }}
            .de-info h2 {{ font-size: 1.25rem; }}
        }}

        @media (max-width: 480px) {{
            .header .container {{ flex-direction: column; gap: 0.75rem; }}
            .header-nav {{ gap: 1rem; }}
            .file-meta {{ flex-direction: column; align-items: flex-start; gap: 0.5rem; }}
        }}
    </style>
</head>
<body>"""
    
    def _generate_main_body(self, sorted_folders: List) -> str:
        """Generate main page body content"""
        total_isos = len([f for folder_files in [folder[1] for folder in sorted_folders] 
                         for f in folder_files if f['iso']])
        
        body = f"""
    <header class="header">
        <div class="container">
            <a href="https://communitybig.org" class="logo">
                Big<span class="text-gradient">Community</span>
            </a>
            <nav class="header-nav">
                <a href="https://communitybig.org">{html.escape(_("Home"))}</a>
                <a href="https://communitybig.org/download.html">{html.escape(_("Download"))}</a>
                <a href="https://github.com/big-comm" target="_blank" rel="noopener">GitHub</a>
            </nav>
        </div>
    </header>

    <section class="hero">
        <div class="container">
            <h1>ISO <span class="text-gradient">Repository</span></h1>
            <p>{html.escape(_("Direct download of BigCommunity ISO images with integrity verification."))}</p>
        </div>
    </section>
    
    <div class="container">
        <div class="stats-bar">
            <div class="stat">
                <i data-lucide="disc-3"></i>
                <span><strong>{total_isos}</strong> {html.escape(_("ISO files available"))}</span>
            </div>
            <div class="stat-divider"></div>
            <div class="stat">
                <i data-lucide="clock"></i>
                <span>{html.escape(_("Updated"))}: {datetime.now().strftime("%Y-%m-%d %H:%M UTC")}</span>
            </div>
        </div>

        <div class="search-wrapper">
            <i data-lucide="search"></i>
            <input type="text" class="search-input" id="searchInput" placeholder="{html.escape(_("Search ISOs..."))}">
        </div>
"""
        
        if not sorted_folders:
            body += f"""
        <div class="empty-state">
            <i data-lucide="inbox"></i>
            <p>{html.escape(_("No ISO files available yet"))}</p>
        </div>
"""
        else:
            for folder_name, folder_files in sorted_folders:
                de_class = self._get_de_css_class(folder_name)
                de_icon = self._get_de_lucide_icon(folder_name)
                iso_count = len([f for f in folder_files if f["iso"]])
                safe_folder = html.escape(folder_name)
                
                body += f"""
        <div class="de-section" data-section="{html.escape(de_class)}">
            <div class="de-header">
                <div class="de-badge {html.escape(de_class)}">
                    <i data-lucide="{html.escape(de_icon)}"></i>
                </div>
                <div class="de-info">
                    <h2>{safe_folder}</h2>
                    <span class="de-count">{iso_count} {html.escape(_("images"))}</span>
                </div>
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
        de_class = self._get_de_css_class(folder_name)
        de_icon = self._get_de_lucide_icon(folder_name)
        safe_folder = html.escape(folder_name)
        
        body = f"""
    <header class="header">
        <div class="container">
            <a href="https://communitybig.org" class="logo">
                Big<span class="text-gradient">Community</span>
            </a>
            <nav class="header-nav">
                <a href="https://communitybig.org">{html.escape(_("Home"))}</a>
                <a href="https://communitybig.org/download.html">{html.escape(_("Download"))}</a>
                <a href="https://github.com/big-comm" target="_blank" rel="noopener">GitHub</a>
            </nav>
        </div>
    </header>

    <section class="hero">
        <div class="container">
            <h1>ISO <span class="text-gradient">Repository</span></h1>
            <p>{html.escape(_("Direct download of BigCommunity ISO images with integrity verification."))}</p>
        </div>
    </section>
    
    <div class="container">
        <div class="breadcrumb">
            <a href="../">{html.escape(_("All Folders"))}</a>
            <span>/</span>
            <strong>{safe_folder}</strong>
        </div>
        
        <div class="de-section">
            <div class="de-header">
                <div class="de-badge {html.escape(de_class)}">
                    <i data-lucide="{html.escape(de_icon)}"></i>
                </div>
                <div class="de-info">
                    <h2>{safe_folder}</h2>
                </div>
            </div>
"""
        
        if grouped_files:
            body += '            <div class="file-grid">\n'
            
            for file_group in sorted(grouped_files, key=lambda x: x['iso']['name'] if x['iso'] else x['md5']['name']):
                if file_group['iso']:
                    body += self._generate_file_card(file_group)
            
            body += '            </div>\n'
        else:
            body += f'            <div class="empty-state"><i data-lucide="inbox"></i><p>{html.escape(_("No files in this folder"))}</p></div>\n'
        
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
                <div class="file-card" data-filename="{safe_name}">
                    <div class="file-card-header">
                        <div class="file-icon">
                            <i data-lucide="disc-3"></i>
                        </div>
                        <div class="file-name">{safe_name}</div>
                    </div>
                    <div class="file-meta">
                        <span class="file-meta-item size">
                            <i data-lucide="hard-drive"></i>
                            {safe_size}
                        </span>
                        <span class="file-meta-item date">
                            <i data-lucide="calendar"></i>
                            {safe_date}
                        </span>
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
                    <div class="md5-section">
                        <div class="md5-label">{html.escape(_("MD5 Checksum"))}</div>
                        <div class="md5-row">
                            <span class="md5-hash">{safe_md5}</span>
                            <button class="md5-copy-btn" onclick="event.stopPropagation(); copyMD5(this, '{safe_md5}')">
                                <i data-lucide="copy"></i>
                            </button>
                        </div>
                    </div>
"""
        
        card += f"""
                    <a class="download-btn" href="{safe_url}" target="_blank" rel="noopener">
                        <i data-lucide="download"></i>
                        {html.escape(_("Download ISO"))}
                    </a>
                </div>
"""
        
        return card
    
    def _generate_html_footer(self) -> str:
        """Generate HTML footer with JavaScript"""
        return f"""
    <footer class="footer">
        <p>{_("Generated by ISOVault")} | <a href="https://communitybig.org">communitybig.org</a></p>
    </footer>

    <div class="toast" id="toast">
        <i data-lucide="check-circle-2"></i>
        <span>{html.escape(_("MD5 copied!"))}</span>
    </div>
    
    <script>
        // Initialize Lucide Icons
        lucide.createIcons();

        // Search
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {{
            searchInput.addEventListener('input', function() {{
                const term = this.value.toLowerCase();
                document.querySelectorAll('.file-card').forEach(card => {{
                    const name = (card.dataset.filename || '').toLowerCase();
                    card.style.display = name.includes(term) ? '' : 'none';
                }});
                document.querySelectorAll('.de-section').forEach(section => {{
                    const visible = section.querySelectorAll('.file-card:not([style*="display: none"])');
                    section.style.display = visible.length === 0 ? 'none' : '';
                }});
            }});
        }}

        // Copy MD5
        function copyMD5(btn, hash) {{
            navigator.clipboard.writeText(hash).then(() => {{
                const toast = document.getElementById('toast');
                toast.classList.add('show');
                setTimeout(() => toast.classList.remove('show'), 2000);
            }});
        }}
    </script>
</body>
</html>"""

    def _get_de_css_class(self, folder_name: str) -> str:
        """Get CSS class for desktop environment badge"""
        classes = {
            "Gnome": "gnome",
            "XFCE": "xfce",
            "Cinnamon": "cinnamon",
            "Root": "root",
        }
        return classes.get(folder_name, "root")

    def _get_de_lucide_icon(self, folder_name: str) -> str:
        """Get Lucide icon name for desktop environment"""
        icons = {
            "Root": "home",
            "Gnome": "layout-grid",
            "Cinnamon": "layers",
            "XFCE": "monitor",
        }
        return icons.get(folder_name, "home")
    
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