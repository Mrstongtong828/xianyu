import React, { useEffect, useState, useRef } from 'react';
import { AIConversation, AIChatSummary } from '../types';
import { getAIConversations, getAIChatList } from '../services/api';
import { Search, RefreshCw, ChevronLeft, ChevronRight, MessageCircle, Bot, User, Settings, Tag } from 'lucide-react';

const roleStyles: Record<string, { bg: string; text: string; icon: React.ReactNode; label: string }> = {
  ai: { bg: 'bg-blue-100', text: 'text-blue-700', icon: <Bot className="w-3 h-3" />, label: 'AI' },
  assistant: { bg: 'bg-blue-100', text: 'text-blue-700', icon: <Bot className="w-3 h-3" />, label: 'AI' },
  user: { bg: 'bg-green-100', text: 'text-green-700', icon: <User className="w-3 h-3" />, label: '买家' },
  buyer: { bg: 'bg-green-100', text: 'text-green-700', icon: <User className="w-3 h-3" />, label: '买家' },
  system: { bg: 'bg-gray-100', text: 'text-gray-500', icon: <Settings className="w-3 h-3" />, label: '系统' },
};

const ConversationList: React.FC = () => {
  const [chats, setChats] = useState<AIChatSummary[]>([]);
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AIConversation[]>([]);
  const [searchText, setSearchText] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const [loadingChats, setLoadingChats] = useState(false);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const msgEndRef = useRef<HTMLDivElement>(null);

  const loadChats = async () => {
    setLoadingChats(true);
    try {
      const res = await getAIChatList();
      if (res.success) {
        setChats(res.data || []);
      }
    } catch (e) {
      console.error('加载对话列表失败:', e);
    } finally {
      setLoadingChats(false);
    }
  };

  const loadMessages = async (chatId: string, p: number = 1) => {
    setLoadingMsgs(true);
    try {
      const res = await getAIConversations({ chat_id: chatId, page: p, page_size: pageSize });
      if (res.success) {
        setMessages(res.data || []);
        setTotal(res.total || 0);
      }
    } catch (e) {
      console.error('加载消息失败:', e);
    } finally {
      setLoadingMsgs(false);
    }
  };

  const handleSearch = async () => {
    if (!searchText.trim()) {
      loadChats();
      return;
    }
    setLoadingChats(true);
    setSelectedChatId(null);
    setMessages([]);
    try {
      const searchLower = searchText.trim().toLowerCase();
      const filteredChats = chats.filter(
        c => c.buyer_id?.toLowerCase().includes(searchLower) || c.chat_id?.toLowerCase().includes(searchLower)
      );
      setChats(filteredChats);
    } finally {
      setLoadingChats(false);
    }
  };

  useEffect(() => {
    loadChats();
  }, []);

  useEffect(() => {
    if (selectedChatId) {
      setPage(1);
      loadMessages(selectedChatId, 1);
    }
  }, [selectedChatId]);

  useEffect(() => {
    if (selectedChatId) {
      loadMessages(selectedChatId, page);
    }
  }, [page]);

  useEffect(() => {
    msgEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const getRoleStyle = (role: string) => {
    return roleStyles[role?.toLowerCase()] || roleStyles.system;
  };

  const formatTime = (ts: string) => {
    if (!ts) return '';
    try {
      const d = new Date(ts);
      const now = new Date();
      const diff = now.getTime() - d.getTime();
      if (diff < 60000) return '刚刚';
      if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
      if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
      return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    } catch {
      return ts;
    }
  };

  return (
    <div className="space-y-4 animate-fade-in">
      <div>
        <h2 className="text-4xl font-extrabold text-gray-900 tracking-tight">对话记录</h2>
        <p className="text-gray-500 mt-2 font-medium">查看AI与买家的历史对话详情。</p>
      </div>

      <div className="ios-card rounded-[2rem] overflow-hidden shadow-lg border-0 bg-white flex" style={{ height: 'calc(100vh - 200px)', minHeight: '600px' }}>
        {/* Left Sidebar - Chat List */}
        <div className="w-80 flex-shrink-0 border-r border-gray-100 flex flex-col bg-[#FAFAFA]">
          <div className="p-4 border-b border-gray-100">
            <div className="relative group">
              <Search className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-[#FFE815] transition-colors" />
              <input
                type="text"
                placeholder="搜索买家ID或会话ID..."
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                className="ios-input pl-10 pr-4 py-2.5 rounded-xl w-full bg-white border-none shadow-sm focus:ring-0 text-sm"
              />
            </div>
            <button
              onClick={handleSearch}
              className="w-full mt-2 px-4 py-2 rounded-xl bg-[#FFE815] text-black font-bold text-sm hover:bg-yellow-400 transition-colors active:scale-95"
            >
              搜索
            </button>
          </div>

          <div className="flex-1 overflow-y-auto">
            {loadingChats ? (
              <div className="flex items-center justify-center py-12">
                <RefreshCw className="w-6 h-6 text-[#FFE815] animate-spin" />
              </div>
            ) : chats.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <MessageCircle className="w-10 h-10 mb-3" />
                <p className="text-sm font-medium">暂无对话记录</p>
              </div>
            ) : (
              chats.map((chat) => (
                <button
                  key={chat.chat_id}
                  onClick={() => {
                    setSelectedChatId(chat.chat_id);
                    setSearchText('');
                  }}
                  className={`w-full text-left px-4 py-3.5 border-b border-gray-50 transition-all hover:bg-white ${
                    selectedChatId === chat.chat_id ? 'bg-white border-l-[3px] border-l-[#FFE815] pl-[13px]' : ''
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-yellow-100 to-yellow-200 flex items-center justify-center flex-shrink-0">
                      <User className="w-4 h-4 text-yellow-700" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="font-bold text-gray-900 text-sm truncate">{chat.buyer_id || '未知买家'}</div>
                      <div className="text-xs text-gray-400 mt-0.5 flex items-center gap-2">
                        <span>{chat.msg_count}条消息</span>
                        <span>{formatTime(chat.last_msg)}</span>
                      </div>
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Right Panel - Messages */}
        <div className="flex-1 flex flex-col bg-white">
          {!selectedChatId ? (
            <div className="flex-1 flex flex-col items-center justify-center text-gray-400">
              <MessageCircle className="w-16 h-16 mb-4 text-gray-200" />
              <p className="text-lg font-bold text-gray-300">选择对话查看详情</p>
              <p className="text-sm mt-1">从左侧列表选择一个会话</p>
            </div>
          ) : (
            <>
              {/* Messages header */}
              <div className="p-4 border-b border-gray-100 flex items-center justify-between bg-white">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-yellow-100 to-yellow-200 flex items-center justify-center">
                    <MessageCircle className="w-5 h-5 text-yellow-700" />
                  </div>
                  <div>
                    <div className="font-bold text-gray-900 text-sm">
                      {chats.find(c => c.chat_id === selectedChatId)?.buyer_id || selectedChatId}
                    </div>
                    <div className="text-xs text-gray-400">会话ID: {selectedChatId.substring(0, 12)}...</div>
                  </div>
                </div>
                <button
                  onClick={() => loadMessages(selectedChatId, page)}
                  className="p-2.5 rounded-xl bg-gray-50 hover:bg-gray-100 text-gray-500 transition-colors"
                >
                  <RefreshCw className={`w-4 h-4 ${loadingMsgs ? 'animate-spin' : ''}`} />
                </button>
              </div>

              {/* Messages body */}
              <div className="flex-1 overflow-y-auto p-6 bg-[#FAFAFA] space-y-4">
                {loadingMsgs ? (
                  <div className="flex items-center justify-center py-20">
                    <RefreshCw className="w-6 h-6 text-[#FFE815] animate-spin" />
                  </div>
                ) : messages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-20 text-gray-400">
                    <MessageCircle className="w-10 h-10 mb-3" />
                    <p className="text-sm font-medium">暂无消息记录</p>
                  </div>
                ) : (
                  messages.map((msg) => {
                    const style = getRoleStyle(msg.role);
                    const isUser = msg.role?.toLowerCase() === 'user' || msg.role?.toLowerCase() === 'buyer';
                    return (
                      <div key={msg.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[75%] ${isUser ? 'items-end' : 'items-start'} flex flex-col gap-1`}>
                          <div className="flex items-center gap-2 mb-0.5">
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-xs font-bold ${style.bg} ${style.text}`}>
                              {style.icon}
                              {style.label}
                            </span>
                            {msg.intent && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-xs font-bold bg-purple-100 text-purple-600">
                                <Tag className="w-3 h-3" />
                                {msg.intent}
                              </span>
                            )}
                          </div>
                          <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                            isUser
                              ? 'bg-[#FFE815] text-black rounded-br-md'
                              : 'bg-white text-gray-800 rounded-bl-md border border-gray-100'
                          }`}>
                            {msg.content}
                          </div>
                          <span className="text-xs text-gray-400 px-1">{formatTime(msg.created_at)}</span>
                        </div>
                      </div>
                    );
                  })
                )}
                <div ref={msgEndRef} />
              </div>

              {/* Pagination */}
              <div className="p-4 border-t border-gray-100 flex items-center justify-between bg-white">
                <div className="text-sm text-gray-500 font-medium">
                  第 {page} 页 / 共 {totalPages} 页 (共 {total} 条)
                </div>
                <div className="flex gap-2">
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage(p => p - 1)}
                    className="p-2.5 rounded-xl bg-gray-50 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed text-gray-600 transition-colors"
                  >
                    <ChevronLeft className="w-5 h-5" />
                  </button>
                  <button
                    disabled={page >= totalPages}
                    onClick={() => setPage(p => p + 1)}
                    className="p-2.5 rounded-xl bg-gray-50 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed text-gray-600 transition-colors"
                  >
                    <ChevronRight className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default ConversationList;
