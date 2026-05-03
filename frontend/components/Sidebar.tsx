import React, { useState } from 'react';
import { LayoutDashboard, Users, ShoppingBag, CreditCard, Settings, LogOut, Box, Sparkles, Zap, MessageSquare, ShieldOff, RotateCw, MessageCircle, Send, Clock, Menu, X, Sun, Moon, ScrollText } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  onLogout: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ activeTab, setActiveTab, onLogout }) => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();

  const menuItems = [
    { id: 'dashboard', icon: LayoutDashboard, label: '仪表盘' },
    { id: 'accounts', icon: Users, label: '账号管理' },
    { id: 'orders', icon: ShoppingBag, label: '订单管理' },
    { id: 'cards', icon: CreditCard, label: '卡密库存' },
    { id: 'items', icon: Box, label: '商品列表' },
    { id: 'item-schedule', icon: Clock, label: '上下架计划' },
    { id: 'keywords', icon: MessageSquare, label: '关键词管理' },
    { id: 'passive-reply', icon: MessageCircle, label: '被动回复记录' },
    { id: 'active-outreach', icon: Send, label: '主动询价' },
    { id: 'logs', icon: ScrollText, label: '操作日志' },
    { id: 'blacklist', icon: ShieldOff, label: '黑名单' },
    { id: 'delivery-retry', icon: RotateCw, label: '发货重试' },
    { id: 'settings', icon: Settings, label: '系统与AI' },
  ];

  const handleTabClick = (tabId: string) => {
    setActiveTab(tabId);
    setMobileMenuOpen(false);
  };

  const sidebarContent = (
    <div className="w-64 h-screen bg-white dark:bg-gray-900 border-r border-gray-100 dark:border-gray-800 flex flex-col justify-between shadow-[4px_0_24px_rgba(0,0,0,0.02)] dark:shadow-[4px_0_24px_rgba(0,0,0,0.3)] transition-colors">
      <div className="p-6">
        <div className="flex items-center gap-3 mb-12 px-2">
          <div className="w-10 h-10 bg-[#FFE815] rounded-xl flex items-center justify-center shadow-lg shadow-yellow-200 transform rotate-[-3deg]">
            <span className="text-black font-extrabold text-xl">闲</span>
          </div>
          <h1 className="text-xl font-extrabold tracking-tight text-gray-900 dark:text-gray-100">广航闲鱼智控 <span className="text-xs bg-black text-[#FFE815] px-1.5 py-0.5 rounded ml-1">PRO</span></h1>
        </div>

        <nav className="space-y-2">
          {menuItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => handleTabClick(item.id)}
                className={`w-full flex items-center gap-3 px-4 py-3.5 rounded-2xl transition-all duration-300 group relative overflow-hidden ${
                  isActive 
                    ? 'bg-[#FFE815] text-black font-bold shadow-lg shadow-yellow-100 transform scale-[1.02]' 
                    : 'text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-100'
                }`}
              >
                <Icon className={`w-5 h-5 transition-colors ${isActive ? 'text-black' : 'text-gray-400 dark:text-gray-500 group-hover:text-gray-600 dark:group-hover:text-gray-300'}`} />
                <span className="text-sm tracking-wide">{item.label}</span>
                {isActive && <Sparkles className="w-4 h-4 absolute right-3 text-black/20 animate-pulse" />}
              </button>
            );
          })}
        </nav>
      </div>

      <div className="p-6 border-t border-gray-50 dark:border-gray-800 space-y-2">
        <button
          onClick={toggleTheme}
          className="w-full flex items-center gap-3 px-4 py-3 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-2xl transition-all duration-200 font-medium"
        >
          {theme === 'light' ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
          <span className="text-sm">{theme === 'light' ? '暗黑模式' : '浅色模式'}</span>
        </button>
        <button 
          onClick={onLogout}
          className="w-full flex items-center gap-3 px-4 py-3 text-gray-500 dark:text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-2xl transition-all duration-200 font-medium"
        >
          <LogOut className="w-5 h-5" />
          <span className="text-sm">退出登录</span>
        </button>
      </div>
    </div>
  );

  return (
    <>
      <button
        onClick={() => setMobileMenuOpen(true)}
        className="md:hidden fixed top-4 left-4 z-50 p-3 bg-white dark:bg-gray-800 rounded-2xl shadow-lg border border-gray-100 dark:border-gray-700"
      >
        <Menu className="w-6 h-6 text-gray-700 dark:text-gray-200" />
      </button>

      {mobileMenuOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/50 dark:bg-black/70 z-40 transition-opacity"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      <div className={`fixed left-0 top-0 h-screen z-50 transition-transform duration-300 ${
        mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
      } md:translate-x-0`}>
        <button
          onClick={() => setMobileMenuOpen(false)}
          className="md:hidden absolute top-4 right-4 z-50 p-2 bg-white dark:bg-gray-800 rounded-xl shadow-lg"
        >
          <X className="w-5 h-5 text-gray-700 dark:text-gray-200" />
        </button>
        {sidebarContent}
      </div>
    </>
  );
};

export default Sidebar;
