"""项目启动入口：

1. 创建 CookieManager，按配置文件 / 环境变量初始化账号任务
2. 在后台线程启动 FastAPI (reply_server) 提供管理与自动回复接口
3. 主协程保持运行

启动参数:
  --max-accounts N     最大同时启动的账号数（默认3）
  --stagger-delay N    账号间启动间隔秒数（默认8秒）
  --pool-size N        浏览器池最大实例数（默认2）
  --quick              跳过非关键的环境检查（Node.js、前端构建）
  --headless           强制无头模式启动浏览器
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path

# 自动安装缺失的核心依赖
try:
    import uvicorn, fastapi, aiohttp, loguru
    import playwright.async_api  # noqa
except ImportError:
    print("[INFO] 检测到缺少依赖，正在自动安装（首次运行需要几分钟）...")
    req = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'requirements.txt')
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', req])
    print("[INFO] 安装完成，请重新运行程序。")
    sys.exit(0)

# ==================== CLI 参数解析 ====================
def _parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='闲鱼超级管家 - 启动入口',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--max-accounts', type=int, default=3,
                        help='最大同时启动的账号数（默认3，设为1最稳定）')
    parser.add_argument('--stagger-delay', type=int, default=8,
                        help='账号间启动间隔秒数（默认8秒）')
    parser.add_argument('--pool-size', type=int, default=2,
                        help='浏览器池最大实例数（默认2）')
    parser.add_argument('--quick', action='store_true',
                        help='跳过非关键的环境检查（Node.js检查、前端构建）')
    parser.add_argument('--headless', action='store_true',
                        help='强制所有浏览器以无头模式运行（减少资源占用）')
    return parser.parse_args()

STARTUP_ARGS = _parse_args()
os.environ['XY_MAX_ACCOUNTS'] = str(STARTUP_ARGS.max_accounts)
os.environ['XY_STAGGER_DELAY'] = str(STARTUP_ARGS.stagger_delay)
os.environ['XY_POOL_SIZE'] = str(STARTUP_ARGS.pool_size)
os.environ['XY_FORCE_HEADLESS'] = '1' if STARTUP_ARGS.headless else '0'
print(f"[INFO] 启动参数: max_accounts={STARTUP_ARGS.max_accounts}, stagger_delay={STARTUP_ARGS.stagger_delay}s, pool_size={STARTUP_ARGS.pool_size}, quick={STARTUP_ARGS.quick}, headless={STARTUP_ARGS.headless}")

# 设置标准输出编码为UTF-8（Windows兼容）
def _setup_console_encoding():
    """设置控制台编码为UTF-8，避免Windows GBK编码问题"""
    if sys.platform == 'win32':
        try:
            # 方法1: 设置环境变量
            os.environ['PYTHONIOENCODING'] = 'utf-8'
            
            # 方法2: 尝试设置控制台代码页为UTF-8
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleOutputCP(65001)  # UTF-8代码页
            except Exception:
                pass
            
            # 方法3: 重新包装stdout和stderr
            try:
                if hasattr(sys.stdout, 'buffer'):
                    import io
                    # 只在编码不是UTF-8时重新包装
                    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
                        sys.stdout = io.TextIOWrapper(
                            sys.stdout.buffer, 
                            encoding='utf-8', 
                            errors='replace',
                            line_buffering=True
                        )
                    if sys.stderr.encoding and sys.stderr.encoding.lower() not in ('utf-8', 'utf8'):
                        sys.stderr = io.TextIOWrapper(
                            sys.stderr.buffer, 
                            encoding='utf-8', 
                            errors='replace',
                            line_buffering=True
                        )
            except Exception:
                pass
        except Exception:
            pass

# 在程序启动时设置编码
_setup_console_encoding()

# ==================== 环境检查 ====================
def _check_python_version():
    """检查 Python 版本是否满足要求"""
    required = (3, 11)
    current = sys.version_info[:2]
    if current < required:
        print(f"[ERROR] Python 版本过低: {sys.version}")
        print(f"        要求 Python >= {required[0]}.{required[1]}，当前 {current[0]}.{current[1]}")
        print(f"        请安装 Python {required[0]}.{required[1]}+ 后重试")
        sys.exit(1)
    print(f"[OK] Python {current[0]}.{current[1]}.{sys.version_info[2]} - 版本满足要求")

def _check_nodejs():
    """检查 Node.js 和 npm 是否安装（前端构建需要）"""
    try:
        result = subprocess.run(
            ['node', '--version'], capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' and hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        if result.returncode == 0:
            print(f"[OK] Node.js {result.stdout.strip()} - 已安装")
            result2 = subprocess.run(
                ['npm', '--version'], capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' and hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            if result2.returncode == 0:
                print(f"[OK] npm {result2.stdout.strip()} - 已安装")
                return True
        print("[WARN] Node.js 未安装或不可用，前端将无法自动构建")
        print("       请安装 Node.js: https://nodejs.org/ (推荐 LTS 版本)")
        print("       安装后重新运行 Start.py 即可")
        return False
    except FileNotFoundError:
        print("[WARN] 未检测到 Node.js，前端将无法自动构建")
        print("       请安装 Node.js: https://nodejs.org/ (推荐 LTS 版本)")
        return False
    except Exception as e:
        print(f"[WARN] Node.js 检查失败: {e}")
        return False

_check_python_version()
_nodejs_available = _check_nodejs() if not STARTUP_ARGS.quick else False

# 定义ASCII安全字符（备用方案）
_OK = '[OK]'
_WARN = '[WARN]'
_ERROR = '[ERROR]'
_INFO = '[INFO]'

# ==================== 在导入任何模块之前先迁移数据库 ====================
def _migrate_database_files_early():
    """在启动前检查并迁移数据库文件到data目录（使用print，因为logger还未初始化）"""
    print("检查数据库文件位置...")
    
    # 确保data目录存在
    data_dir = Path("data")
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        print(f"{_OK} 创建 data 目录")
    
    # 定义需要迁移的文件
    files_to_migrate = [
        ("xianyu_data.db", "data/xianyu_data.db", "主数据库"),
    ]
    
    migrated_files = []
    
    # 迁移主数据库和统计数据库
    for old_path, new_path, description in files_to_migrate:
        old_file = Path(old_path)
        new_file = Path(new_path)
        
        if old_file.exists():
            if not new_file.exists():
                # 新位置不存在，移动文件
                try:
                    shutil.move(str(old_file), str(new_file))
                    print(f"{_OK} 迁移{description}: {old_path} -> {new_path}")
                    migrated_files.append(description)
                except Exception as e:
                    print(f"{_WARN} 无法迁移{description}: {e}")
                    print(f"  尝试复制文件...")
                    try:
                        shutil.copy2(str(old_file), str(new_file))
                        print(f"{_OK} 已复制{description}到新位置")
                        print(f"  请在确认数据正常后手动删除: {old_path}")
                        migrated_files.append(f"{description}(已复制)")
                    except Exception as e2:
                        print(f"{_ERROR} 复制{description}失败: {e2}")
            else:
                # 新位置已存在，检查旧文件大小
                try:
                    if old_file.stat().st_size > 0:
                        print(f"{_WARN} 发现旧{description}文件: {old_path}")
                        print(f"  新数据库位于: {new_path}")
                        print(f"  建议备份后删除旧文件")
                except Exception:
                    pass
    
    # 迁移备份文件
    backup_files = list(Path(".").glob("xianyu_data_backup_*.db"))
    if backup_files:
        print(f"发现 {len(backup_files)} 个备份文件")
        backup_migrated = 0
        for backup_file in backup_files:
            new_backup_path = data_dir / backup_file.name
            if not new_backup_path.exists():
                try:
                    shutil.move(str(backup_file), str(new_backup_path))
                    print(f"{_OK} 迁移备份文件: {backup_file.name}")
                    backup_migrated += 1
                except Exception as e:
                    print(f"{_WARN} 无法迁移备份文件 {backup_file.name}: {e}")
        
        if backup_migrated > 0:
            migrated_files.append(f"{backup_migrated}个备份文件")
    
    # 输出迁移总结
    if migrated_files:
        print(f"{_OK} 数据库迁移完成，已迁移: {', '.join(migrated_files)}")
    else:
        print(f"{_OK} 数据库文件检查完成")
    
    return True

# 在导入 db_manager 之前先执行数据库迁移
try:
    _migrate_database_files_early()
except Exception as e:
    print(f"{_WARN} 数据库迁移检查失败: {e}")
    # 继续启动，因为可能是首次运行

# ==================== 检查并安装Playwright浏览器 ====================
def _check_and_install_playwright():
    """检查Playwright浏览器是否存在，如果不存在则自动安装"""
    print("检查Playwright浏览器...")
    
    # 检查是否安装了playwright模块
    try:
        import playwright
    except ImportError:
        print(f"{_WARN} Playwright模块未安装，跳过浏览器检查")
        return False
    
    # 检查Playwright浏览器是否存在
    playwright_installed = False
    possible_paths = []
    
    # 如果是打包后的exe，优先检查exe同目录
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        playwright_dir = exe_dir / 'playwright'
        possible_paths.insert(0, playwright_dir)  # 插入到最前面，优先检查
        
        # 检查exe同目录的浏览器是否完整
        if playwright_dir.exists():
            chromium_dirs = list(playwright_dir.glob('chromium-*'))
            if chromium_dirs:
                chromium_dir = chromium_dirs[0]
                chrome_exe = chromium_dir / 'chrome-win' / 'chrome.exe'
                if chrome_exe.exists() and chrome_exe.stat().st_size > 0:
                    print(f"{_OK} 找到已提取的Playwright浏览器: {chrome_exe}")
                    print(f"{_INFO} 浏览器版本: {chromium_dir.name}")
                    # 清除可能存在的旧环境变量，使用实际存在的浏览器
                    if 'PLAYWRIGHT_BROWSERS_PATH' in os.environ:
                        old_path = os.environ['PLAYWRIGHT_BROWSERS_PATH']
                        if old_path != str(playwright_dir):
                            print(f"{_INFO} 清除旧的环境变量: {old_path}")
                            del os.environ['PLAYWRIGHT_BROWSERS_PATH']
                    # 确保环境变量已设置
                    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(playwright_dir)
                    print(f"{_INFO} 已设置PLAYWRIGHT_BROWSERS_PATH: {playwright_dir}")
                    playwright_installed = True
                    return True
    
    # Windows上的常见位置
    if sys.platform == 'win32':
        # 用户缓存目录
        user_cache = Path.home() / '.cache' / 'ms-playwright'
        possible_paths.append(user_cache)
        
        # LocalAppData目录
        local_appdata = os.getenv('LOCALAPPDATA')
        if local_appdata:
            possible_paths.append(Path(local_appdata) / 'ms-playwright')
        
        # AppData目录
        appdata = os.getenv('APPDATA')
        if appdata:
            possible_paths.append(Path(appdata) / 'ms-playwright')
    
    # 检查是否存在chromium浏览器
    for path in possible_paths:
        if path.exists():
            # 查找chromium目录
            chromium_dirs = list(path.glob('chromium-*'))
            if chromium_dirs:
                for chromium_dir in chromium_dirs:
                    chrome_win = chromium_dir / 'chrome-win'
                    chrome_exe = chrome_win / 'chrome.exe'
                    if chrome_exe.exists():
                        print(f"{_OK} 找到Playwright浏览器: {chrome_exe}")
                        # 设置环境变量
                        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(path)
                        playwright_installed = True
                        break
                if playwright_installed:
                    break
    
    # 如果没找到，尝试使用playwright命令检查
    if not playwright_installed:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(headless=True)
                    browser.close()
                    print(f"{_OK} Playwright浏览器已安装（通过API检测）")
                    playwright_installed = True
                except Exception:
                    pass
        except Exception:
            pass
    
    # 如果没找到，先尝试从临时目录提取（如果是打包的exe）
    if not playwright_installed and getattr(sys, 'frozen', False):
        try:
            exe_dir = Path(sys.executable).parent
            playwright_dir = exe_dir / 'playwright'
            
            if hasattr(sys, '_MEIPASS'):
                temp_dir = Path(sys._MEIPASS)
                temp_playwright = temp_dir / 'playwright'
                
                if temp_playwright.exists():
                    # 查找所有 chromium 相关目录（包括 chromium-* 和 chromium_headless_shell-*）
                    temp_chromium_dirs = list(temp_playwright.glob('chromium*'))
                    if temp_chromium_dirs:
                        print(f"{_INFO} 检测到打包的浏览器文件，正在提取...")
                        playwright_dir.mkdir(parents=True, exist_ok=True)
                        extracted_count = 0
                        
                        for temp_chromium_dir in temp_chromium_dirs:
                            temp_chrome_win = temp_chromium_dir / 'chrome-win'
                            
                            # 检查完整版或 headless_shell 版
                            temp_chrome_exe = temp_chrome_win / 'chrome.exe'
                            temp_headless_exe = temp_chrome_win / 'headless_shell.exe'
                            
                            # 验证文件是否存在
                            is_valid = False
                            if temp_chromium_dir.name.startswith('chromium_headless_shell'):
                                is_valid = temp_headless_exe.exists() and temp_headless_exe.stat().st_size > 0
                            else:
                                is_valid = temp_chrome_exe.exists() and temp_chrome_exe.stat().st_size > 0
                            
                            if is_valid:
                                target_chromium_dir = playwright_dir / temp_chromium_dir.name
                                
                                if not target_chromium_dir.exists():
                                    try:
                                        shutil.copytree(temp_chromium_dir, target_chromium_dir, dirs_exist_ok=True)
                                        
                                        # 验证提取的文件
                                        if temp_chromium_dir.name.startswith('chromium_headless_shell'):
                                            target_exe = target_chromium_dir / 'chrome-win' / 'headless_shell.exe'
                                        else:
                                            target_exe = target_chromium_dir / 'chrome-win' / 'chrome.exe'
                                        
                                        if target_exe.exists() and target_exe.stat().st_size > 0:
                                            print(f"{_OK} 浏览器文件提取成功: {target_exe}")
                                            print(f"{_INFO} 浏览器版本: {temp_chromium_dir.name}")
                                            extracted_count += 1
                                    except Exception as e:
                                        print(f"{_WARN} 提取 {temp_chromium_dir.name} 失败: {e}")
                        
                        if extracted_count > 0:
                            # 清除可能存在的旧环境变量
                            if 'PLAYWRIGHT_BROWSERS_PATH' in os.environ:
                                old_path = os.environ['PLAYWRIGHT_BROWSERS_PATH']
                                print(f"{_INFO} 清除旧的环境变量: {old_path}")
                                del os.environ['PLAYWRIGHT_BROWSERS_PATH']
                            # 设置新的环境变量
                            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(playwright_dir)
                            print(f"{_INFO} 已提取 {extracted_count} 个浏览器版本")
                            print(f"{_INFO} 已设置PLAYWRIGHT_BROWSERS_PATH: {playwright_dir}")
                            playwright_installed = True
                            return True
        except Exception as e:
            print(f"{_WARN} 提取浏览器文件时出错: {e}")
    
    # 如果没找到，尝试安装
    if not playwright_installed:
        print(f"{_WARN} 未找到Playwright浏览器，正在自动安装...")
        print("   这可能需要几分钟时间，请耐心等待...")
        
        try:
            # 方法1: 尝试使用playwright的Python API安装（推荐，适用于打包后的exe）
            try:
                # 直接调用playwright的安装函数
                from playwright._impl._driver import install_driver, install_browsers
                print("   正在安装Playwright驱动...")
                install_driver()
                print("   正在安装Chromium浏览器...")
                install_browsers(['chromium'])
                print(f"{_OK} Playwright浏览器安装成功（通过API）")
                playwright_installed = True
            except ImportError:
                # 如果API不可用，使用命令行方式
                print("   使用命令行方式安装...")
                import subprocess
                
                # 尝试使用playwright的安装命令
                # 对于打包后的exe，playwright模块应该已经包含
                creation_flags = 0
                if sys.platform == 'win32' and hasattr(subprocess, 'CREATE_NO_WINDOW'):
                    creation_flags = subprocess.CREATE_NO_WINDOW
                
                result = subprocess.run(
                    [sys.executable, '-m', 'playwright', 'install', 'chromium'],
                    capture_output=True,
                    text=True,
                    timeout=600,  # 10分钟超时
                    creationflags=creation_flags
                )
                
                if result.returncode == 0:
                    print(f"{_OK} Playwright浏览器安装成功")
                    playwright_installed = True
                else:
                    print(f"{_WARN} Playwright浏览器安装失败")
                    if result.stdout:
                        print(f"   输出: {result.stdout[-500:]}")  # 只显示最后500字符
                    if result.stderr:
                        print(f"   错误: {result.stderr[-500:]}")
                    print("   您可以稍后手动运行: playwright install chromium")
                    return False
            except Exception as api_error:
                # API安装失败，尝试命令行方式
                print(f"   API安装失败，尝试命令行方式: {api_error}")
                import subprocess
                
                creation_flags = 0
                if sys.platform == 'win32' and hasattr(subprocess, 'CREATE_NO_WINDOW'):
                    creation_flags = subprocess.CREATE_NO_WINDOW
                
                result = subprocess.run(
                    [sys.executable, '-m', 'playwright', 'install', 'chromium'],
                    capture_output=True,
                    text=True,
                    timeout=600,
                    creationflags=creation_flags
                )
                
                if result.returncode == 0:
                    print(f"{_OK} Playwright浏览器安装成功（通过命令行）")
                    playwright_installed = True
                else:
                    print(f"{_WARN} Playwright浏览器安装失败")
                    if result.stdout:
                        print(f"   输出: {result.stdout[-500:]}")
                    if result.stderr:
                        print(f"   错误: {result.stderr[-500:]}")
                    print("   您可以稍后手动运行: playwright install chromium")
                    return False
            except ImportError:
                # 如果playwright模块不可用，尝试使用subprocess
                import subprocess
                result = subprocess.run(
                    [sys.executable, '-m', 'playwright', 'install', 'chromium'],
                    capture_output=True,
                    text=True,
                    timeout=600,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' and hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                
                if result.returncode == 0:
                    print(f"{_OK} Playwright浏览器安装成功")
                    playwright_installed = True
                else:
                    print(f"{_WARN} Playwright浏览器安装失败")
                    if result.stdout:
                        print(f"   输出: {result.stdout}")
                    if result.stderr:
                        print(f"   错误: {result.stderr}")
                    print("   您可以稍后手动运行: playwright install chromium")
                    return False
                
        except subprocess.TimeoutExpired:
            print(f"{_WARN} Playwright浏览器安装超时（超过10分钟）")
            print("   您可以稍后手动运行: playwright install chromium")
            return False
        except Exception as e:
            print(f"{_WARN} Playwright浏览器安装失败: {e}")
            import traceback
            print(f"   详细错误: {traceback.format_exc()}")
            print("   您可以稍后手动运行: playwright install chromium")
            return False
    
    return playwright_installed

# 检查并安装Playwright浏览器
try:
    _check_and_install_playwright()
except Exception as e:
    print(f"{_WARN} Playwright浏览器检查失败: {e}")
    print("   程序将继续启动，但Playwright功能可能不可用")
    # 继续启动，不影响主程序运行

# ==================== 自动构建前端 ====================
def _build_frontend():
    """自动安装依赖并构建前端"""
    xy_dir = Path("xy")
    frontend_dir = Path("frontend")
    static_dir = Path("static")

    # 优先使用 xy 目录，如果不存在则使用 frontend
    if xy_dir.exists():
        build_dir = xy_dir
        print(f"{_INFO} 使用 xy 目录作为前端源")
    elif frontend_dir.exists():
        build_dir = frontend_dir
        print(f"{_INFO} 使用 frontend 目录作为前端源")
    else:
        print(f"{_WARN} xy 和 frontend 目录都不存在，跳过前端构建")
        return False

    print("检查前端构建状态...")

    # 如果 Node.js 不可用，跳过构建
    if not _nodejs_available:
        if static_dir.exists() and (static_dir / "index.html").exists():
            print(f"[OK] 前端已构建，跳过（无需 Node.js）")
            return True
        else:
            print(f"[WARN] 前端未构建且 Node.js 不可用，跳过构建")
            print(f"       前端页面将无法访问。请安装 Node.js 后重新运行：")
            print(f"       https://nodejs.org/")
            return False

    # 检查是否需要重新构建
    need_build = False

    # 如果 static 目录不存在，需要构建
    if not static_dir.exists():
        need_build = True
        print(f"{_INFO} static 目录不存在，需要构建前端")
    else:
        # 检查 index.html 是否存在
        index_html = static_dir / "index.html"
        if not index_html.exists():
            need_build = True
            print(f"{_INFO} static/index.html 不存在，需要构建前端")
        else:
            print(f"{_OK} 前端已构建，跳过")

    # 如果不需要构建，直接返回
    if not need_build:
        return True

    # 开始构建前端
    print(f"{_INFO} 开始构建前端...")
    print(f"   源目录: {build_dir}")
    print(f"   1. 安装 npm 依赖...")

    try:
        import subprocess

        # 设置 Windows 下的 subprocess 参数
        creation_flags = 0
        if sys.platform == 'win32' and hasattr(subprocess, 'CREATE_NO_WINDOW'):
            creation_flags = subprocess.CREATE_NO_WINDOW

        # 1. npm install
        try:
            result = subprocess.run(
                ['npm', 'install'],
                cwd=str(build_dir),
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                creationflags=creation_flags
            )

            if result.returncode == 0:
                print(f"{_OK} npm 依赖安装成功")
            else:
                print(f"{_WARN} npm install 失败")
                if result.stdout:
                    print(f"   输出: {result.stdout[-500:]}")
                if result.stderr:
                    print(f"   错误: {result.stderr[-500:]}")
                return False
        except subprocess.TimeoutExpired:
            print(f"{_WARN} npm install 超时（超过5分钟）")
            return False
        except FileNotFoundError:
            print(f"{_WARN} 未找到 npm，请确保已安装 Node.js 和 npm")
            print(f"   你可以手动运行: cd {build_dir} && npm install && npm run build")
            return False
        except Exception as e:
            print(f"{_WARN} npm install 失败: {e}")
            return False

        # 2. npm run build
        print(f"   2. 构建前端...")
        try:
            result = subprocess.run(
                ['npm', 'run', 'build'],
                cwd=str(build_dir),
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                creationflags=creation_flags
            )

            if result.returncode == 0:
                print(f"{_OK} 前端构建成功")
                return True
            else:
                print(f"{_WARN} npm run build 失败")
                if result.stdout:
                    print(f"   输出: {result.stdout[-500:]}")
                if result.stderr:
                    print(f"   错误: {result.stderr[-500:]}")
                return False
        except subprocess.TimeoutExpired:
            print(f"{_WARN} npm run build 超时（超过5分钟）")
            return False
        except Exception as e:
            print(f"{_WARN} npm run build 失败: {e}")
            return False

    except Exception as e:
        print(f"{_WARN} 前端构建过程出错: {e}")
        return False


# 尝试构建前端（--quick 模式跳过）
if not STARTUP_ARGS.quick:
    try:
        build_success = _build_frontend()
        if not build_success:
            print(f"{_WARN} 前端构建失败，程序将继续启动但前端可能不可用")
    except Exception as e:
        print(f"{_WARN} 前端构建检查失败: {e}")
        print("   程序将继续启动，但前端可能不可用")
else:
    print(f"{_INFO} --quick 模式，跳过前端构建检查")

# ==================== 系统资源检查 ====================
def _check_system_resources():
    """检查系统可用资源，在低资源时给出警告和建议"""
    try:
        import psutil
        mem = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=0.5)
        available_gb = mem.available / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)

        print(f"{_INFO} 系统资源: CPU {cpu_percent:.1f}%, 可用内存 {available_gb:.1f}GB / {total_gb:.1f}GB")

        # 每个浏览器实例大约占用 300-500MB
        est_memory_per_account = 0.4
        max_safe_accounts = max(1, int(available_gb / est_memory_per_account))
        configured_accounts = STARTUP_ARGS.max_accounts

        if available_gb < 1.0:
            print(f"{_WARN} 可用内存不足1GB，强烈建议只启动1个账号!")
            print(f"      推荐: python Start.py --max-accounts 1 --pool-size 1 --headless")
            os.environ['XY_MAX_ACCOUNTS'] = '1'
            os.environ['XY_POOL_SIZE'] = '1'
        elif configured_accounts > max_safe_accounts:
            suggested = max(1, max_safe_accounts - 1)
            print(f"{_WARN} 当前可用内存仅支持约 {max_safe_accounts} 个账号，但配置了 {configured_accounts} 个")
            print(f"      建议: python Start.py --max-accounts {suggested} --pool-size {suggested}")
            os.environ['XY_MAX_ACCOUNTS'] = str(suggested)
            os.environ['XY_POOL_SIZE'] = str(min(suggested, STARTUP_ARGS.pool_size))

        # 设置进程优先级（Windows）
        if sys.platform == 'win32':
            try:
                import ctypes
                # BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.GetCurrentProcess()
                kernel32.SetPriorityClass(handle, 0x00004000)
                print(f"{_INFO} 已将当前进程优先级设为'低于正常'，减少对系统的影响")
            except Exception:
                pass

        return True
    except ImportError:
        print(f"{_WARN} psutil 未安装，跳过系统资源检查")
        return False

_check_system_resources()

# ==================== 现在可以安全地导入其他模块 ====================
import asyncio
import signal
import threading
import time
import traceback as _traceback
import uvicorn
from urllib.parse import urlparse
from loguru import logger

# 修复Linux环境下的asyncio子进程问题
if sys.platform.startswith('linux'):
    try:
        # 在程序启动时就设置正确的事件循环策略
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
        logger.debug("已设置事件循环策略以支持子进程")
    except Exception as e:
        logger.debug(f"设置事件循环策略失败: {e}")

from config import AUTO_REPLY, COOKIES_LIST
import cookie_manager as cm
from db_manager import db_manager
from file_log_collector import setup_file_logging


def _start_api_server():
    """后台线程启动 FastAPI 服务（带自动重启）"""
    api_conf = AUTO_REPLY.get('api', {})

    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', '8000'))

    if 'host' in api_conf:
        host = api_conf['host']
    if 'port' in api_conf:
        port = api_conf['port']

    if 'url' in api_conf and 'host' not in api_conf and 'port' not in api_conf:
        url = api_conf.get('url', 'http://0.0.0.0:8000/xianyu/reply')
        parsed = urlparse(url)
        if parsed.hostname and parsed.hostname != 'localhost':
            host = parsed.hostname
        port = parsed.port or 8000

    MAX_RESTART_ATTEMPTS = 5
    RESTART_DELAY_BASE = 2
    restart_count = 0

    while restart_count < MAX_RESTART_ATTEMPTS:
        try:
            logger.info(f"启动Web服务器: http://{host}:{port} (第{restart_count + 1}次)")
            config = uvicorn.Config("reply_server:app", host=host, port=port, log_level="info")
            server = uvicorn.Server(config)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            server.loop = loop
            loop.run_until_complete(server.serve())
        except Exception as e:
            restart_count += 1
            if restart_count >= MAX_RESTART_ATTEMPTS:
                logger.error(f"uvicorn服务器在{MAX_RESTART_ATTEMPTS}次尝试后仍失败，放弃重启: {e}")
                break
            delay = RESTART_DELAY_BASE * restart_count
            logger.warning(f"uvicorn服务器异常退出，{delay}秒后重试 ({restart_count}/{MAX_RESTART_ATTEMPTS}): {e}")
            time.sleep(delay)
        else:
            restart_count += 1
            delay = RESTART_DELAY_BASE * restart_count
            logger.warning(f"uvicorn服务器正常退出，{delay}秒后重试 ({restart_count}/{MAX_RESTART_ATTEMPTS})")
            time.sleep(delay)




def load_keywords_file(path: str):
    """从文件读取关键字 -> [(keyword, reply)]"""
    kw_list = []
    p = Path(path)
    if not p.exists():
        return kw_list
    with p.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '\t' in line:
                k, r = line.split('\t', 1)
            elif ' ' in line:
                k, r = line.split(' ', 1)
            elif ':' in line:
                k, r = line.split(':', 1)
            else:
                continue
            kw_list.append((k.strip(), r.strip()))
    return kw_list


async def main():
    print("开始启动主程序...")

    # 初始化文件日志收集器
    print("初始化文件日志收集器...")
    setup_file_logging()
    logger.info("文件日志收集器已启动，开始收集实时日志")

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    async def _shutdown():
        if shutdown_event.is_set():
            return
        shutdown_event.set()
        logger.info("收到关闭信号，开始优雅关闭...")

        # 取消所有运行中的任务
        tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"已取消 {len(tasks)} 个运行中的任务")

        # 关闭浏览器池
        try:
            from utils.browser_pool import _global_browser_pool
            if _global_browser_pool:
                await _global_browser_pool.close_all()
                logger.info("浏览器池已关闭")
        except Exception as e:
            logger.warning(f"关闭浏览器池失败: {e}")

        # 关闭数据库连接
        try:
            db_manager.close()
            logger.info("数据库连接已关闭")
        except Exception:
            pass

        loop.stop()

    def _signal_handler():
        loop.call_soon_threadsafe(lambda: asyncio.ensure_future(_shutdown()))

    try:
        if sys.platform != 'win32':
            loop.add_signal_handler(signal.SIGTERM, _signal_handler)
        loop.add_signal_handler(signal.SIGINT, _signal_handler)
    except (NotImplementedError, RuntimeError):
        signal.signal(signal.SIGINT, lambda s, f: _signal_handler())
        if sys.platform != 'win32':
            signal.signal(signal.SIGTERM, lambda s, f: _signal_handler())

    # 创建 CookieManager 并在全局暴露
    print("创建 CookieManager...")
    cm.manager = cm.CookieManager(loop)
    manager = cm.manager
    print("CookieManager 创建完成")

    # ====== 先启动 API 服务（让用户第一时间能访问界面） ======
    print("启动 API 服务线程...")
    port = int(os.getenv('API_PORT', AUTO_REPLY.get('api', {}).get('port', 8000)))
    threading.Thread(target=_start_api_server, daemon=True).start()
    print("API 服务线程已启动")

    # 等待 API 服务就绪
    print("等待 API 服务就绪...")
    import urllib.request
    for _ in range(30):
        await asyncio.sleep(0.5)
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/api/feishu/command?challenge=health')
            print(f"{_OK} API 服务已就绪: http://127.0.0.1:{port}")
            break
        except Exception:
            pass

    # ====== 启动信息汇总 ======
    host = os.getenv('API_HOST', '0.0.0.0')
    print("=" * 55)
    print("  闲鱼超级管家 启动成功!")
    print(f"  本地访问: http://127.0.0.1:{port}")
    if host != '127.0.0.1' and host != 'localhost':
        import socket
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
            print(f"  局域网访问: http://{local_ip}:{port}")
        except Exception:
            pass
    print(f"  默认管理员: admin")
    print(f"  按 Ctrl+C 停止服务")
    print("=" * 55)

    # 延迟打开浏览器
    import webbrowser
    threading.Timer(1.0, lambda: webbrowser.open(f'http://127.0.0.1:{port}')).start()

    # ====== 阶梯式启动账号任务（后台进行，不阻塞界面访问） ======
    enabled_accounts = []
    for cid, val in manager.cookies.items():
        if not manager.get_cookie_status(cid):
            logger.info(f"跳过禁用的 Cookie: {cid}")
            continue
        enabled_accounts.append((cid, val))

    max_accounts = int(os.getenv('XY_MAX_ACCOUNTS', '3'))
    stagger_delay = int(os.getenv('XY_STAGGER_DELAY', '8'))

    if len(enabled_accounts) > max_accounts:
        print(f"{_WARN} 检测到 {len(enabled_accounts)} 个启用账号，将只启动前 {max_accounts} 个")
        print(f"      如需启动更多，请使用: python Start.py --max-accounts {len(enabled_accounts)}")

    started_count = 0
    for idx, (cid, val) in enumerate(enabled_accounts):
        if started_count >= max_accounts:
            logger.warning(f"已达到最大账号数限制 ({max_accounts})，跳过剩余 {len(enabled_accounts) - started_count} 个账号")
            break

        if idx > 0:
            print(f"等待 {stagger_delay} 秒后再启动下一个账号...")
            await asyncio.sleep(stagger_delay)

        try:
            from db_manager import db_manager
            cookie_info = db_manager.get_cookie_details(cid)
            user_id = cookie_info.get('user_id') if cookie_info else None

            print(f"[{started_count + 1}/{min(len(enabled_accounts), max_accounts)}] 正在启动账号: {cid}...")
            task = loop.create_task(manager._run_xianyu(cid, val, user_id))
            manager.tasks[cid] = task
            started_count += 1
            print(f"{_OK} 账号 {cid} 已启动 (用户ID: {user_id}), 当前任务数: {len(manager.tasks)}")
        except Exception as e:
            logger.error(f"启动 Cookie 任务失败: {cid}, {e}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")

    print(f"{_OK} 账号启动完毕: {started_count} 个运行中")

    # 如果配置文件中有新的 Cookie（不在数据库中的），也加载它们
    for entry in COOKIES_LIST:
        cid = entry.get('id')
        val = entry.get('value')
        if not cid or not val or cid in manager.cookies:
            continue

        kw_file = entry.get('keywords_file')
        kw_list = load_keywords_file(kw_file) if kw_file else None
        if len(manager.tasks) >= max_accounts:
            logger.warning(f"已达到最大账号数限制 ({max_accounts})，跳过配置文件账号: {cid}")
            continue
        manager.add_cookie(cid, val, kw_list)
        logger.info(f"从配置文件加载 Cookie: {cid}")

    # 若老环境变量仍提供单账号 Cookie，则作为 default 账号
    env_cookie = os.getenv('COOKIES_STR')
    if env_cookie and 'default' not in manager.list_cookies():
        if len(manager.tasks) < max_accounts:
            manager.add_cookie('default', env_cookie)
            logger.info("从环境变量加载 default Cookie")
        else:
            logger.warning(f"已达到最大账号数限制 ({max_accounts})，跳过环境变量 Cookie")

    # 启动任务心跳监控
    import time as _time_module
    async def _task_watchdog():
        """定期检查任务健康状况，记录异常但不断开"""
        while not shutdown_event.is_set():
            await asyncio.sleep(30)
            try:
                manager = cm.manager
                if manager:
                    dead_tasks = []
                    for cid, task in list(manager.tasks.items()):
                        if task.done():
                            exc = task.exception()
                            if exc:
                                logger.error(f"检测到任务异常退出: {cid}, 错误: {exc}")
                                dead_tasks.append(cid)
                            else:
                                logger.warning(f"检测到任务意外退出: {cid}")
                                dead_tasks.append(cid)
                    if dead_tasks:
                        logger.warning(f"共 {len(dead_tasks)} 个任务退出: {dead_tasks}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"任务看门狗检查失败: {e}")

    watchdog_task = asyncio.ensure_future(_task_watchdog())

    await shutdown_event.wait()
    watchdog_task.cancel()
    try:
        await watchdog_task
    except asyncio.CancelledError:
        pass
    logger.info("主程序已退出")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] 用户中断，程序退出")
    except Exception as _main_error:
        print(f"\n[CRITICAL] 主程序异常退出: {_main_error}")
        _traceback.print_exc()
        sys.exit(1)
    finally:
        print("[INFO] 程序已退出")