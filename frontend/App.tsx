import React, { useState, useEffect, Suspense, lazy } from 'react';
import Sidebar from './components/Sidebar';
import ErrorBoundary from './components/ErrorBoundary';
import { login, verifyToken, register, sendVerificationCode, getWechatQRCode, checkWechatStatus, bindWechat } from './services/api';
import { ShieldCheck, ArrowRight, Loader2, User, Lock, Mail, QrCode, KeyRound, ArrowLeft, CheckCircle, X } from 'lucide-react';
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
const ActiveOutreach = lazy(() => import('./components/ActiveOutreach'));
const ItemSchedule = lazy(() => import('./components/ItemSchedule'));
const OperationLogs = lazy(() => import('./components/OperationLogs'));

const PageFallback = () => (
  <div className="flex items-center justify-center py-20">
    <Loader2 className="w-8 h-8 text-[#FFE815] animate-spin" />
  </div>
);

type PageMode = 'login' | 'register' | 'wechat-bind';

const App: React.FC = () => {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [checkingAuth, setCheckingAuth] = useState(true);
  
  // Login state
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState('');
  
  // Page mode: login / register / wechat-bind
  const [pageMode, setPageMode] = useState<PageMode>('login');
  
  // Register state
  const [regUsername, setRegUsername] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regCode, setRegCode] = useState('');
  const [regLoading, setRegLoading] = useState(false);
  const [regError, setRegError] = useState('');
  const [regSuccess, setRegSuccess] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  
  // WeChat state
  const [showWechatQR, setShowWechatQR] = useState(false);
  const [wechatQRCode, setWechatQRCode] = useState('');
  const [wechatState, setWechatState] = useState('');
  const [wechatLoading, setWechatLoading] = useState(false);
  const [wechatError, setWechatError] = useState('');
  
  useEffect(() => {
      const token = localStorage.getItem('auth_token');
      if (token) {
          verifyToken()
            .then((res) => {
              if (res && res.authenticated) {
                setIsLoggedIn(true);
              } else {
                localStorage.removeItem('auth_token');
              }
            })
            .catch(() => localStorage.removeItem('auth_token'))
            .finally(() => setCheckingAuth(false));
      } else {
          setCheckingAuth(false);
      }
      
      const handleLogout = () => setIsLoggedIn(false);
      window.addEventListener('auth:logout', handleLogout);
      return () => window.removeEventListener('auth:logout', handleLogout);
  }, []);

  // WeChat polling
  useEffect(() => {
    if (!wechatState) return;
    const interval = setInterval(async () => {
      try {
        const res = await checkWechatStatus(wechatState);
        if (res.status === 'scanned' && res.token) {
          clearInterval(interval);
          localStorage.setItem('auth_token', res.token);
          setShowWechatQR(false);
          setWechatState('');
          setIsLoggedIn(true);
        } else if (res.status === 'expired') {
          clearInterval(interval);
          setWechatError('二维码已过期，请刷新');
          setWechatLoading(false);
        }
      } catch (e) { /* ignore polling errors */ }
    }, 2000);
    return () => clearInterval(interval);
  }, [wechatState]);

  // Check localStorage for WeChat bind data
  useEffect(() => {
    const interval = setInterval(() => {
      const bindData = localStorage.getItem('wechat_bind_data');
      if (bindData && isLoggedIn) {
        try {
          const data = JSON.parse(bindData);
          bindWechat(data).then(() => {
            localStorage.removeItem('wechat_bind_data');
            localStorage.removeItem('wechat_login');
          }).catch(() => {});
        } catch (e) {}
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [isLoggedIn]);

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

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!regUsername || !regEmail || !regPassword || !regCode) {
      setRegError('请填写所有字段');
      return;
    }
    setRegLoading(true);
    setRegError('');
    try {
      const res = await register({ username: regUsername, email: regEmail, password: regPassword, verification_code: regCode });
      if (res.success) {
        setRegSuccess(true);
      } else {
        setRegError(res.message || '注册失败');
      }
    } catch (err) {
      setRegError('无法连接服务器');
    } finally {
      setRegLoading(false);
    }
  };

  const handleSendCode = async () => {
    if (!regEmail) {
      setRegError('请先输入邮箱');
      return;
    }
    setSendingCode(true);
    setRegError('');
    try {
      const res = await sendVerificationCode({ email: regEmail, type: 'register' });
      if (res.success) {
        setCodeSent(true);
      } else {
        setRegError(res.message || '发送失败');
      }
    } catch (err) {
      setRegError('发送验证码失败');
    } finally {
      setSendingCode(false);
    }
  };

  const handleWechatLogin = async () => {
    setShowWechatQR(true);
    setWechatLoading(true);
    setWechatError('');
    try {
      const res = await getWechatQRCode();
      if (res.success && res.qrcode) {
        setWechatQRCode(res.qrcode);
        setWechatState(res.state!);
        setWechatLoading(false);
      } else {
        setWechatError(res.message || '获取二维码失败');
        setWechatLoading(false);
      }
    } catch (err) {
      setWechatError('无法连接服务器');
      setWechatLoading(false);
    }
  };

  const switchToRegister = () => {
    setPageMode('register');
    setRegSuccess(false);
    setRegError('');
    setCodeSent(false);
  };

  const switchToLogin = () => {
    setPageMode('login');
    setLoginError('');
  };

  // -- Login page (with register and WeChat options) --
  if (!isLoggedIn && !checkingAuth) {
    // Registration success page
    if (pageMode === 'register' && regSuccess) {
      return (
        <ThemeProvider>
        <div className="min-h-screen flex items-center justify-center bg-[#F4F5F7] dark:bg-gray-950 p-4">
          <div className="bg-white/80 dark:bg-gray-900/80 backdrop-blur-3xl p-8 md:p-12 rounded-[3rem] shadow-[0_20px_60px_-15px_rgba(0,0,0,0.05)] dark:shadow-[0_20px_60px_-15px_rgba(0,0,0,0.3)] w-full max-w-md border border-white dark:border-gray-800 text-center">
            <CheckCircle className="w-20 h-20 text-green-500 mx-auto mb-6" />
            <h2 className="text-2xl font-bold mb-3 text-gray-900 dark:text-white">注册成功</h2>
            <p className="text-gray-500 dark:text-gray-400 mb-8">账号已创建，请登录</p>
            <button onClick={switchToLogin} className="ios-button w-full h-14 bg-[#FFE815] text-black font-bold rounded-2xl hover:bg-yellow-400 transition-all">
              前往登录
            </button>
          </div>
        </div>
        </ThemeProvider>
      );
    }

    // Registration form
    if (pageMode === 'register') {
      return (
        <ThemeProvider>
        <div className="min-h-screen flex items-center justify-center bg-[#F4F5F7] dark:bg-gray-950 p-4 relative overflow-hidden font-sans">
          <div className="absolute top-[-10%] left-[-10%] w-[60%] h-[60%] bg-blue-200/40 rounded-full blur-[120px] animate-pulse dark:opacity-30"></div>
          <div className="absolute bottom-[-10%] right-[-10%] w-[60%] h-[60%] bg-yellow-200/30 rounded-full blur-[120px] animate-pulse dark:opacity-20" style={{animationDelay: '2s'}}></div>
          
          <div className="bg-white/80 dark:bg-gray-900/80 backdrop-blur-3xl p-8 md:p-12 rounded-[3rem] shadow-[0_20px_60px_-15px_rgba(0,0,0,0.05)] dark:shadow-[0_20px_60px_-15px_rgba(0,0,0,0.3)] w-full max-w-lg border border-white dark:border-gray-800 relative z-10">
            <button onClick={switchToLogin} className="flex items-center gap-2 text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white mb-6 transition-colors">
              <ArrowLeft className="w-5 h-5" /> 返回登录
            </button>
            
            <div className="text-center mb-8">
              <h2 className="text-3xl font-extrabold text-gray-900 dark:text-gray-100 mb-2 tracking-tight">注册账号</h2>
              <p className="text-gray-500 dark:text-gray-400 font-medium">创建您的闲鱼管家账号</p>
            </div>
            
            <form onSubmit={handleRegister} className="space-y-4">
              <div className="relative group">
                <User className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 group-focus-within:text-black dark:group-focus-within:text-white transition-colors" />
                <input type="text" placeholder="用户名" value={regUsername} onChange={e => setRegUsername(e.target.value)}
                  className="w-full ios-input pl-14 pr-6 py-4.5 rounded-2xl text-base h-14 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-700" />
              </div>
              <div className="relative group">
                <Mail className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 group-focus-within:text-black dark:group-focus-within:text-white transition-colors" />
                <input type="email" placeholder="邮箱" value={regEmail} onChange={e => setRegEmail(e.target.value)}
                  className="w-full ios-input pl-14 pr-6 py-4.5 rounded-2xl text-base h-14 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-700" />
              </div>
              <div className="relative group">
                <Lock className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 group-focus-within:text-black dark:group-focus-within:text-white transition-colors" />
                <input type="password" placeholder="密码" value={regPassword} onChange={e => setRegPassword(e.target.value)}
                  className="w-full ios-input pl-14 pr-6 py-4.5 rounded-2xl text-base h-14 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-700" />
              </div>
              <div className="flex gap-3">
                <div className="relative group flex-1">
                  <KeyRound className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 group-focus-within:text-black dark:group-focus-within:text-white transition-colors" />
                  <input type="text" placeholder="验证码" value={regCode} onChange={e => setRegCode(e.target.value)}
                    className="w-full ios-input pl-14 pr-4 py-4.5 rounded-2xl text-base h-14 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-700" />
                </div>
                <button type="button" onClick={handleSendCode} disabled={sendingCode}
                  className="px-4 h-14 rounded-2xl bg-gray-100 dark:bg-gray-800 text-sm font-bold text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors whitespace-nowrap disabled:opacity-50">
                  {sendingCode ? '发送中...' : codeSent ? '已发送' : '获取验证码'}
                </button>
              </div>
              
              {regError && (
                <div className="p-3 rounded-xl bg-red-50 dark:bg-red-900/30 text-red-500 dark:text-red-400 text-sm text-center font-bold">
                  {regError}
                </div>
              )}
              
              <button type="submit" disabled={regLoading}
                className="ios-button w-full h-14 bg-[#FFE815] text-black font-bold rounded-2xl hover:bg-yellow-400 transition-all flex items-center justify-center gap-2 disabled:opacity-50 text-lg">
                {regLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : null} 注册
              </button>
            </form>
          </div>
        </div>
        </ThemeProvider>
      );
    }

    // Login form (default)
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
                        placeholder="用户名" 
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
              className="ios-button w-full h-14 bg-[#FFE815] text-black font-bold rounded-2xl hover:bg-yellow-400 transition-all flex items-center justify-center gap-2 disabled:opacity-50 text-lg"
            >
                {loginLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <ArrowRight className="w-5 h-5" />}
                登录
            </button>

            {/* WeChat Login Button */}
            <button type="button" onClick={handleWechatLogin}
              className="w-full h-14 bg-[#07C160] text-white font-bold rounded-2xl hover:bg-[#06AD56] transition-all flex items-center justify-center gap-2">
              <QrCode className="w-5 h-5" /> 微信扫码登录
            </button>
          </form>

          {/* Register link */}
          <p className="text-center mt-6 text-sm text-gray-400 dark:text-gray-500">
            还没有账号？{' '}
            <button onClick={switchToRegister} className="text-[#FFE815] font-bold hover:underline">
              立即注册
            </button>
          </p>
        </div>

        {/* WeChat QR Code Modal */}
        {showWechatQR && (
          <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowWechatQR(false)}>
            <div className="bg-white dark:bg-gray-900 rounded-[2rem] p-8 w-full max-w-sm text-center relative" onClick={e => e.stopPropagation()}>
              <button onClick={() => setShowWechatQR(false)} className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
                <X className="w-6 h-6" />
              </button>
              <h3 className="text-xl font-bold mb-4 text-gray-900 dark:text-white">微信扫码登录</h3>
              {wechatLoading ? (
                <div className="py-12"><Loader2 className="w-8 h-8 mx-auto animate-spin text-[#FFE815]" /></div>
              ) : wechatError ? (
                <div className="py-12 text-red-500">{wechatError}</div>
              ) : (
                <div>
                  <img src={`data:image/png;base64,${wechatQRCode}`} alt="微信二维码" className="w-48 h-48 mx-auto rounded-xl" />
                  <p className="text-sm text-gray-400 mt-4">请使用微信扫描二维码</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      </ThemeProvider>
    );
  }

  if (checkingAuth) {
      return (
          <ThemeProvider>
              <div className="min-h-screen flex items-center justify-center bg-[#f5f5f7] dark:bg-gray-950">
                  <Loader2 className="w-8 h-8 text-[#FFE815] animate-spin" />
              </div>
          </ThemeProvider>
      );
  }

  // -- Main App (logged in) --
  return (
      <ThemeProvider>
      <div className="flex min-h-screen bg-[#F4F5F7] dark:bg-gray-950 font-sans">
        <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />
        <main className="flex-1 ml-0 md:ml-[280px] px-4 pt-6 pb-24">
          <ErrorBoundary>
            <Suspense fallback={<PageFallback />}>
              {activeTab === 'dashboard' && <Dashboard />}
              {activeTab === 'accounts' && <AccountList />}
              {activeTab === 'orders' && <OrderList />}
              {activeTab === 'cards' && <CardList />}
              {activeTab === 'items' && <ItemList />}
              {activeTab === 'settings' && <Settings />}
              {activeTab === 'keywords' && <Keywords />}
              {activeTab === 'blacklist' && <Blacklist />}
              {activeTab === 'delivery-retry' && <DeliveryRetryQueue />}
              {activeTab === 'conversations' && <ConversationList />}
              {activeTab === 'outreach' && <ActiveOutreach />}
              {activeTab === 'schedules' && <ItemSchedule />}
              {activeTab === 'logs' && <OperationLogs />}
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
      </ThemeProvider>
  );
};

export default App;
