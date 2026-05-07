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
    parser.add_argument('--skip-browser-check', action='store_true',
                        help='跳过Playwright浏览器检查')
    parser.add_argument('--skip-frontend', action='store_true',
                        help='跳过前端构建')
    parser.add_argument('--no-resource-check', action='store_true',
                        help='跳过系统资源检查')
    return parser.parse_args()

STARTUP_ARGS = _parse_args()
os.environ['XY_MAX_ACCOUNTS'] = str(STARTUP_ARGS.max_accounts)
os.environ['XY_STAGGER_DELAY'] = str(STARTUP_ARGS.stagger_delay)
os.environ['XY_POOL_SIZE'] = str(STARTUP_ARGS.pool_size)
os.environ['XY_FORCE_HEADLESS'] = '1' if STARTUP_ARGS.headless else '0'
print(f"[INFO] 启动参数: max_accounts={STARTUP_ARGS.max_accounts}, stagger_delay={STARTUP_ARGS.stagger_delay}s, pool_size={STARTUP_ARGS.pool_size}, quick={STARTUP_ARGS.quick}, headless={STARTUP_ARGS.headless}, skip_browser={STARTUP_ARGS.skip_browser_check}, skip_frontend={STARTUP_ARGS.skip_frontend}, no_resource_check={STARTUP_ARGS.no_resource_check}")

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
_nodejs_available = _check_nodejs()

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

# ==================== 查找Playwright浏览器 ====================
def _find_playwright_browser():
    """查找Playwright浏览器，返回路径或None"""
    # 方法1: 使用Playwright内置API检测
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
                return True  # API检测成功
            except Exception:
                pass
    except Exception:
        pass
    
    # 方法2: 检查常见Windows路径（仅2个）
    paths_to_check = []
    local_appdata = os.getenv('LOCALAPPDATA')
    if local_appdata:
        paths_to_check.append(Path(local_appdata) / 'ms-playwright')
    paths_to_check.append(Path.home() / '.cache' / 'ms-playwright')
    
    for path in paths_to_check:
        if path.exists():
            chromium_dirs = list(path.glob('chromium-*'))
            for chromium_dir in chromium_dirs:
                chrome_exe = chromium_dir / 'chrome-win' / 'chrome.exe'
                if chrome_exe.exists():
                    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(path)
                    return str(chrome_exe)
    return None


# ==================== 检查并安装Playwright浏览器 ====================
def _check_and_install_playwright():
    """检查Playwright浏览器是否存在，如果不存在则尝试自动安装"""
    print("检查Playwright浏览器...")
    
    try:
        import playwright
    except ImportError:
        print(f"{_WARN} Playwright模块未安装，跳过浏览器检查")
        return False
    
    browser_path = _find_playwright_browser()
    if browser_path:
        if isinstance(browser_path, str):
            print(f"{_OK} 找到Playwright浏览器: {browser_path}")
        else:
            print(f"{_OK} Playwright浏览器已安装（通过API检测）")
        return True
    
    print(f"{_WARN} Playwright浏览器未安装，请手动运行: playwright install chromium")
    
    # 尝试自动安装
    try:
        from playwright._impl._driver import install_driver, install_browsers
        print("   正在自动安装Playwright浏览器...")
        install_driver()
        install_browsers(['chromium'])
        print(f"{_OK} Playwright浏览器安装成功（通过API）")
        return True
    except ImportError:
        pass
    except Exception as api_error:
        print(f"   API安装失败，尝试命令行方式: {api_error}")
    
    # 命令行安装（120s超时）
    try:
        creation_flags = 0
        if sys.platform == 'win32' and hasattr(subprocess, 'CREATE_NO_WINDOW'):
            creation_flags = subprocess.CREATE_NO_WINDOW
        
        result = subprocess.run(
            [sys.executable, '-m', 'playwright', 'install', 'chromium'],
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=creation_flags
        )
        
        if result.returncode == 0:
            print(f"{_OK} Playwright浏览器安装成功（通过命令行）")
            return True
        else:
            if result.stderr:
                print(f"   错误: {result.stderr[-500:]}")
    except subprocess.TimeoutExpired:
        print(f"   安装超时（超过120秒）")
    except Exception as e:
        print(f"   安装失败: {e}")
    
    print("   请手动运行: playwright install chromium")
    return False

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
                timeout=120,
                creationflags=creation_flags
            )

            if result.returncode == 0:
                print(f"{_OK} npm 依赖安装成功")
            else:
                print(f"{_WARN} npm install 失败，尝试使用淘宝镜像...")
                try:
                    result2 = subprocess.run(
                        ['npm', 'install', '--registry=https://registry.npmmirror.com'],
                        cwd=str(build_dir),
                        capture_output=True,
                        text=True,
                        timeout=120,
                        creationflags=creation_flags
                    )
                    if result2.returncode == 0:
                        print(f"{_OK} npm 依赖安装成功（淘宝镜像）")
                    else:
                        print(f"{_WARN} npm install 失败")
                        if result2.stderr:
                            print(f"   错误: {result2.stderr[-500:]}")
                        print(f"   请手动运行: cd {build_dir} && npm install && npm run build")
                        return False
                except subprocess.TimeoutExpired:
                    print(f"{_WARN} npm install（淘宝镜像）超时")
                    print(f"   请手动运行: cd {build_dir} && npm install && npm run build")
                    return False
        except subprocess.TimeoutExpired:
            print(f"{_WARN} npm install 超时（超过120秒）")
            print(f"   请手动运行: cd {build_dir} && npm install && npm run build")
            return False
        except FileNotFoundError:
            print(f"{_WARN} 未找到 npm，请确保已安装 Node.js 和 npm")
            print(f"   请手动运行: cd {build_dir} && npm install && npm run build")
            return False
        except Exception as e:
            print(f"{_WARN} npm install 失败: {e}")
            print(f"   请手动运行: cd {build_dir} && npm install && npm run build")
            return False

        # 2. npm run build
        print(f"   2. 构建前端...")
        try:
            result = subprocess.run(
                ['npm', 'run', 'build'],
                cwd=str(build_dir),
                capture_output=True,
                text=True,
                timeout=120,
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
                print(f"   请手动运行: cd {build_dir} && npm run build")
                return False
        except subprocess.TimeoutExpired:
            print(f"{_WARN} npm run build 超时（超过120秒）")
            print(f"   请手动运行: cd {build_dir} && npm run build")
            return False
        except Exception as e:
            print(f"{_WARN} npm run build 失败: {e}")
            print(f"   请手动运行: cd {build_dir} && npm run build")
            return False

    except Exception as e:
        print(f"{_WARN} 前端构建过程出错: {e}")
        return False

# ==================== 系统资源检查 ====================
def _check_system_resources():
    """检查系统可用资源，在低资源时给出警告和建议"""
    if STARTUP_ARGS.no_resource_check:
        print(f"{_INFO} --no-resource-check，跳过系统资源检查")
        return False
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

# ==================== 启动前综合检查 ====================
def _run_preflight_checks():
    """集中执行所有启动前检查并报告结果"""
    results = {}

    # Playwright浏览器检查
    if not STARTUP_ARGS.skip_browser_check:
        try:
            pw_ok = _check_and_install_playwright()
            results['Playwright浏览器'] = 'PASS' if pw_ok else 'WARN (功能可能不可用)'
        except Exception as e:
            print(f"{_WARN} Playwright浏览器检查失败: {e}")
            results['Playwright浏览器'] = 'WARN (检查异常)'
    else:
        results['Playwright浏览器'] = 'SKIP'

    # 前端构建检查
    if STARTUP_ARGS.skip_frontend or STARTUP_ARGS.quick:
        results['前端构建'] = 'SKIP'
    else:
        try:
            build_ok = _build_frontend()
            if not build_ok:
                print(f"{_WARN} 前端构建失败，程序将继续启动但前端可能不可用")
            results['前端构建'] = 'PASS' if build_ok else 'WARN (前端可能不可用)'
        except Exception as e:
            print(f"{_WARN} 前端构建检查失败: {e}")
            results['前端构建'] = 'WARN (检查异常)'

    # 系统资源检查
    if not STARTUP_ARGS.no_resource_check:
        try:
            res_ok = _check_system_resources()
            results['系统资源'] = 'PASS' if res_ok else 'WARN'
        except Exception as e:
            print(f"{_WARN} 系统资源检查失败: {e}")
            results['系统资源'] = 'WARN (检查异常)'
    else:
        results['系统资源'] = 'SKIP'

    # 打印检查结果汇总
    print()
    print("=" * 50)
    print("  启动前检查结果:")
    for name, status in results.items():
        tag = _OK if status.startswith('PASS') else _INFO if status.startswith('SKIP') else _WARN
        print(f"  {tag} {name}: {status}")
    print("=" * 50)
    print()

_run_preflight_checks()

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
    port = int(os.getenv('API_PORT', '8080'))
    port_source = '环境变量 API_PORT'

    if 'host' in api_conf:
        host = api_conf['host']
    if 'port' in api_conf:
        port = api_conf['port']
        port_source = '配置文件 AUTO_REPLY.api.port'

    logger.info(f"Web管理界面: http://{host}:{port} (来源: {port_source})")

    MAX_RESTART_ATTEMPTS = 5
    RESTART_DELAY_BASE = 2
    restart_count = 0

    while restart_count < MAX_RESTART_ATTEMPTS:
        loop = None
        try:
            logger.info(f"启动Web服务器: http://{host}:{port} (第{restart_count + 1}次)")
            config = uvicorn.Config(
                "reply_server:app",
                host=host,
                port=port,
                log_level="info",
                timeout_keep_alive=5,       # 5秒后关闭空闲keep-alive连接，防止CLOSE_WAIT累积
                limit_concurrency=100,       # 限制并发连接数
                backlog=128,                # TCP连接队列大小
                timeout_graceful_shutdown=10 # 优雅关闭超时
            )
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
        finally:
            if loop is not None:
                try:
                    loop.close()
                except Exception:
                    pass




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

    # ====== 启动配置摘要 ======
    print("=" * 50)
    print("  启动配置")
    print("=" * 50)
    print(f"  最大账号数:    {STARTUP_ARGS.max_accounts}")
    print(f"  启动间隔:      {STARTUP_ARGS.stagger_delay}秒")
    print(f"  浏览器池大小:  {STARTUP_ARGS.pool_size}")
    print(f"  无头模式:      {'是' if STARTUP_ARGS.headless else '否'}")
    print(f"  快速启动:      {'是' if STARTUP_ARGS.quick else '否'}")
    print(f"  强制无头:      {'是' if os.getenv('XY_FORCE_HEADLESS') == '1' else '否'}")
    print(f"  数据加密:      {'是' if os.getenv('XY_DATA_ENCRYPT', '0') == '1' else '否'}")
    print(f"  调试模式:      {'是' if os.getenv('XY_DEBUG', '0') == '1' else '否'}")
    print("=" * 50)
    print()

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

    if sys.platform == 'win32':
        _shutdown_flag = threading.Event()

        def _win_signal_handler(signum, frame):
            _shutdown_flag.set()

        signal.signal(signal.SIGINT, _win_signal_handler)
        signal.signal(signal.SIGTERM, _win_signal_handler)
        logger.info("Windows: 使用轮询方式监听 Ctrl+C / 终止信号")

        async def _win_poll_shutdown():
            while not _shutdown_flag.is_set() and not shutdown_event.is_set():
                await asyncio.sleep(0.5)
            if _shutdown_flag.is_set() and not shutdown_event.is_set():
                logger.info("检测到 Ctrl+C，开始优雅关闭...")
                await _shutdown()

        asyncio.ensure_future(_win_poll_shutdown())
    else:
        try:
            loop.add_signal_handler(signal.SIGTERM, _signal_handler)
            loop.add_signal_handler(signal.SIGINT, _signal_handler)
        except (NotImplementedError, RuntimeError):
            signal.signal(signal.SIGINT, lambda s, f: _signal_handler())
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
    health_ok = False
    async with aiohttp.ClientSession() as session:
        for _ in range(20):
            await asyncio.sleep(0.5)
            try:
                async with session.get(
                    f'http://127.0.0.1:{port}/api/feishu/command?challenge=health',
                    timeout=aiohttp.ClientTimeout(total=2)
                ) as resp:
                    if resp.status == 200:
                        print(f"{_OK} API 服务已就绪: http://127.0.0.1:{port}")
                        health_ok = True
                        break
            except Exception:
                pass

    if not health_ok:
        print(f"{_WARN} API 服务健康检查超时（20次重试），将继续启动但界面可能暂时不可用")
        logger.warning("API 服务健康检查超时，将继续启动但界面可能暂时不可用")

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
    failed_accounts = []

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
            error_msg = str(e)
            if 'session' in error_msg.lower() or 'expired' in error_msg.lower():
                reason = 'Session过期'
            elif 'cookie' in error_msg.lower():
                reason = 'Cookie无效'
            elif 'login' in error_msg.lower():
                reason = '登录失败'
            elif 'browser' in error_msg.lower():
                reason = '浏览器启动失败'
            elif 'timeout' in error_msg.lower():
                reason = '超时'
            else:
                reason = error_msg[:30]

            failed_accounts.append((cid, reason))
            logger.error(f"启动账号失败: {cid}, {e}")
            logger.error(f"详细错误信息: {_traceback.format_exc()}")
            print(f"{_ERROR} 账号 {cid} 启动失败 ({reason})，继续启动下一个账号...")

    print(f"{_OK} 账号启动完毕: {started_count} 个运行中", end='')
    if failed_accounts:
        print(f", {len(failed_accounts)} 个失败")
        for fcid, freason in failed_accounts:
            print(f"  失败账号: {fcid} ({freason})")
    else:
        print()

    # ====== 启动报告 ======
    print()
    print("============ 启动报告 ============")
    print(f"  API 服务:     http://127.0.0.1:{port}  {'[OK]' if health_ok else '[WARN]'}")
    total_to_show = min(len(enabled_accounts), max_accounts) if enabled_accounts else 0
    print(f"  已启动账号:   {started_count}/{total_to_show}")
    failed_cids = {fc[0] for fc in failed_accounts}
    for idx, (scid, _sval) in enumerate(enabled_accounts):
        if idx >= max_accounts:
            break
        if scid in failed_cids:
            sreason = next((fc[1] for fc in failed_accounts if fc[0] == scid), '未知')
            print(f"    ✗ {scid} ({sreason})")
        elif scid in manager.tasks:
            print(f"    ✓ {scid}")
    try:
        import psutil
        mem = psutil.virtual_memory()
        print(f"  系统资源:     可用内存 {mem.available / (1024**3):.1f}GB / {mem.total / (1024**3):.1f}GB")
    except ImportError:
        pass
    print(f"  浏览器池:     最大 {STARTUP_ARGS.pool_size} 个实例")
    print("=================================")
    print()

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