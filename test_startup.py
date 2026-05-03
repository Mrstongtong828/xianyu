#!/usr/bin/env python3
"""
简单测试脚本 - 检查 FastAPI 应用能否启动
"""
import sys
import os

# Add project to path
project_path = "/mnt/e/xianyu-super-butler"
sys.path.insert(0, project_path)

print("测试 FastAPI 应用启动...")
print("=" * 60)

try:
    # Try to import FastAPI
    from fastapi import FastAPI
    print("✓ FastAPI 导入成功")
    
    # Try to create a simple app
    app = FastAPI(title="Test App")
    print("✓ FastAPI 应用创建成功")
    
    # Try to add a simple route
    @app.get("/")
    def read_root():
        return {"Hello": "World"}
    
    print("✓ 路由添加成功")
    
    # Try to import uvicorn
    import uvicorn
    print("✓ uvicorn 导入成功")
    
    print("\n基本 FastAPI 应用可以启动！")
    print("现在尝试导入项目模块...")
    
    # Try to import project modules one by one
    modules_to_try = [
        ("loguru", "logger"),
        ("psutil", "psutil"),
        ("passlib", "passlib"),
    ]
    
    for module_name, import_name in modules_to_try:
        try:
            __import__(module_name)
            print(f"✓ {module_name} 导入成功")
        except ImportError as e:
            print(f"✗ {module_name} 导入失败: {e}")
    
    # Try to import shared.py
    print("\n尝试导入 shared.py...")
    try:
        # First, let's check what's in shared.py that might fail
        import importlib.util
        spec = importlib.util.spec_from_file_location("shared", os.path.join(project_path, "shared.py"))
        shared_module = importlib.util.module_from_spec(spec)
        
        # Try to execute the module
        spec.loader.exec_module(shared_module)
        print("✓ shared.py 导入成功")
    except Exception as e:
        print(f"✗ shared.py 导入失败: {e}")
        print(f"错误类型: {type(e).__name__}")
        
        # Try to identify the specific import that's failing
        import traceback
        print("\n详细错误信息:")
        traceback.print_exc()
    
except Exception as e:
    print(f"✗ 测试失败: {e}")
    import traceback
    traceback.print_exc()