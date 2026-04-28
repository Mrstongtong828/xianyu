import React, { useState, useEffect, Suspense, lazy } from 'react';
import Sidebar from './components/Sidebar';
import { login, verifyToken } from './services/api';
import { ShieldCheck, ArrowRight, Loader2, User, Lock, KeyRound } from 'lucide-react';
import { ThemeProvider } from './context/ThemeContext';

const Dashboard = lazy(() => import('./components/Dashboard'));
const AccountList = lazy(() => import('./components/AccountList'));
const OrderList = lazy(() => import('./components/OrderList'));
const CardList = lazy(() => import('./components/CardList'));
const ItemList = lazy(() => import('./components/ItemList'));
const Settings = lazy(() => import('./components/Settings'));
const Keywords = lazy(() => import('./components/Keywords'));
const Blacklist = lazy(() => import('./components/Blacklist'));
const DeliveryRetryQueue = lazy(() => import('./components/DeliveryRetryQueue'));
const ConversationList = lazy(() => import('./components/ConversationList'));
const ItemSchedule = lazy(() => import('./components/ItemSchedule'));
const OperationLogs = lazy(() => import('./components/OperationLogs'));

const PageFallback = () => (
  <div className="flex items-center justify-center py-20">
    <Loader2 className="w-8 h-8 text-[#FFE815] animate-spin" />
  </div>
);

const App: React.FC = () => {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState('');

  useEffect(() => {
      const token = localStorage.getItem('auth_token');
      if (token) {
          verifyToken()
            .then(() => setIsLoggedIn(true))
            .catch(() => localStorage.removeItem('auth_token'))
            .finally(() => setCheckingAuth(false));
      } else {
          setCheckingAuth(false);
      }
      
      const handleLogout = () => setIsLoggedIn(false);
      window.addEventListener('auth:logout', handleLogout);
      return () => window.removeEventListener('auth:logout', handleLogout);
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
      e.preventDefault();
      setLoginLoading(true);
      setLoginError('');
      
      try {
          const res = await login({ username, password });
          if (res.success && res.token) {
              localStorage.setItem('auth_token', res.token);
              setIsLoggedIn(true);
          } else {
              setLoginError(res.message || '登录失败');
          }
      } catch (err) {
          setLoginError('无法连接服务器');
      } finally {
          setLoginLoading(false);
      }
  };

  const handleTestEntry = () => {
      setLoginLoading(true);
      setTimeout(() => {
          localStorage.setItem('auth_token', 'test_token');
          setIsLoggedIn(true);
          setLoginLoading(false);
      }, 800);
  };

  if (checkingAuth) {
      return (
          <ThemeProvider>
              <div className="min-h-screen flex items-center justify-center bg-[#f5f5f7] dark:bg-gray-950">
                  <Loader2 className="w-8 h-8 text-[#FFE815] animate-spin" />
              </div>
          </ThemeProvider>
      );
  }

  if (!isLoggedIn) {
    return (
      <ThemeProvider>
      <div className="min-h-screen flex items-center justify-center bg-[#F4F5F7] dark:bg-gray-950 p-4 relative overflow-hidden font-sans transition-colors">
        <div className="absolute top-[-10%] left-[-10%] w-[60%] h-[60%] bg-yellow-200/40 rounded-full blur-[120px] animate-pulse dark:opacity-30"></div>
        <div className="absolute bottom-[-10%] right-[-10%] w-[60%] h-[60%] bg-blue-200/30 rounded-full blur-[120px] animate-pulse dark:opacity-20" style={{animationDelay: '2s'}}></div>

        <div className="bg-white/80 dark:bg-gray-900/80 backdrop-blur-3xl p-8 md:p-12 rounded-[3rem] shadow-[0_20px_60px_-15px_rgba(0,0,0,0.05)] dark:shadow-[0_20px_60px_-15px_rgba(0,0,0,0.3)] w-full max-w-lg border border-white dark:border-gray-800 relative z-10 animate-fade-in">
          
          <div className="text-center mb-10">
             <div className="w-24 h-24 bg-[#FFE815] rounded-[2rem] flex items-center justify-center shadow-xl shadow-yellow-200 mx-auto mb-6 transform rotate-[-6deg] hover:rotate-0 transition-all duration-500 cursor-pointer group">
                <span className="text-black font-extrabold text-5xl group-hover:scale-110 transition-transform">闲</span>
             </div>
             <h2 className="text-3xl font-extrabold text-gray-900 dark:text-gray-100 mb-2 tracking-tight">欢迎回来</h2>
             <p className="text-gray-500 dark:text-gray-400 font-medium">闲鱼智能自动发货与管家系统</p>
          </div>
          
          <form onSubmit={handleLogin} className="space-y-5">
            <div className="space-y-4">
                <div className="relative group">
                    <User className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 group-focus-within:text-black dark:group-focus-within:text-white transition-colors" />
                    <input 
                        type="text" 
                        placeholder="管理员账号" 
                        value={username}
                        onChange={e => setUsername(e.target.value)}
                        className="w-full ios-input pl-14 pr-6 py-4.5 rounded-2xl text-base h-14 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-700"
                    />
                </div>
                <div className="relative group">
                    <Lock className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 group-focus-within:text-black dark:group-focus-within:text-white transition-colors" />
                    <input 
                        type="password" 
                        placeholder="密码" 
                        value={password}
                        onChange={e => setPassword(e.target.value)}
                        className="w-full ios-input pl-14 pr-6 py-4.5 rounded-2xl text-base h-14 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-700"
                    />
                </div>
            </div>
            
            {loginError && (
                <div className="p-3 rounded-xl bg-red-50 dark:bg-red-900/30 text-red-500 dark:text-red-400 text-sm text-center font-bold flex items-center justify-center gap-2">
                    <ShieldCheck className="w-4 h-4" /> {loginError}
                </div>
            )}

            <button 
              type="submit" 
              disabled={loginLoading}
              className="w-full ios-btn-primary h-14 rounded-2xl text-lg shadow-xl shadow-yellow-200 mt-2 flex items-center justify-center gap-2 group disabled:opacity-70"
            >
              {loginLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <>立即登录 <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" /></>}
            </button>
          </form>
          
          <div className="mt-8 pt-6 border-t border-gray-100 dark:border-gray-800">
             <button 
                type="button"
                onClick={handleTestEntry}
                disabled={loginLoading}
                className="w-full bg-black dark:bg-white dark:text-black text-white h-14 rounded-2xl text-base font-bold shadow-lg shadow-gray-200 flex items-center justify-center gap-2 hover:bg-gray-800 dark:hover:bg-gray-200 transition-all active:scale-95"
             >
                <KeyRound className="w-5 h-5 text-[#FFE815]" />
                游客试用 (无需账号)
             </button>
             <div className="mt-6 text-center">
                 <span className="text-xs text-gray-400 dark:text-gray-500 font-medium tracking-widest uppercase">
                    Xianyu Auto-Dispatch Pro v2.5
                 </span>
             </div>
          </div>
        </div>
      </div>
      </ThemeProvider>
    );
  }

  const renderContent = () => {
    const content = (() => {
      switch (activeTab) {
        case 'dashboard': return <Dashboard />;
        case 'accounts': return <AccountList />;
        case 'orders': return <OrderList />;
        case 'cards': return <CardList />;
        case 'items': return <ItemList />;
        case 'keywords': return <Keywords />;
        case 'blacklist': return <Blacklist />;
        case 'conversations': return <ConversationList />;
        case 'item-schedule': return <ItemSchedule />;
        case 'logs': return <OperationLogs />;
        case 'delivery-retry': return <DeliveryRetryQueue />;
        case 'settings': return <Settings />;
        default: return <Dashboard />;
      }
    })();
    return <Suspense fallback={<PageFallback />}>{content}</Suspense>;
  };

  return (
    <ThemeProvider>
    <div className="flex min-h-screen bg-[#F4F5F7] dark:bg-gray-950 text-[#111] dark:text-gray-100 transition-colors">
      <Sidebar 
        activeTab={activeTab} 
        setActiveTab={setActiveTab} 
        onLogout={() => {
            localStorage.removeItem('auth_token');
            setIsLoggedIn(false);
        }} 
      />
      
      <main className="flex-1 ml-0 md:ml-64 p-4 md:p-8 lg:p-12 overflow-y-auto h-screen relative scroll-smooth">
        <div className="fixed top-0 right-0 w-[800px] h-[800px] bg-gradient-to-bl from-yellow-50 dark:from-yellow-900/10 to-transparent rounded-full blur-[120px] pointer-events-none -z-10 opacity-60"></div>
        
        <div className="max-w-[1400px] mx-auto pb-10">
            {renderContent()}
        </div>
      </main>
    </div>
    </ThemeProvider>
  );
};

export default App;
