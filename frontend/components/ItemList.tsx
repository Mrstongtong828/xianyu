import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Item, AccountDetail } from '../types';
import { getItems, getAccountDetails, syncItemsFromAccount } from '../services/api';
import { Box, RefreshCw, ShoppingBag, Edit, Trash2, Plus, Save, X, Eye, EyeOff } from 'lucide-react';

const ItemList: React.FC = () => {
  const STORAGE_KEY = 'item_list_form';
  const savedForm = (() => { try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); } catch { return {}; } })();

  const [items, setItems] = useState<Item[]>([]);
  const [accounts, setAccounts] = useState<AccountDetail[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>(savedForm.selectedAccount || '');
  const [loading, setLoading] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedItem, setSelectedItem] = useState<Item | null>(null);
  const [editForm, setEditForm] = useState<Partial<Item>>({});
  const [addForm, setAddForm] = useState({
    cookie_id: '',
    item_id: '',
    item_title: '',
    item_price: '',
    item_image: '',
    is_multi_spec: false,
    is_multi_qty_ship: false
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ selectedAccount }));
  }, [selectedAccount]);

  useEffect(() => {
    getAccountDetails().then(setAccounts);
    getItems().then(setItems);
  }, []);

  const handleSync = async () => {
      if (!selectedAccount) return alert('请先选择账号');
      setLoading(true);
      await syncItemsFromAccount(selectedAccount);
      getItems().then(setItems);
      setLoading(false);
  };

  const handleEdit = (item: Item) => {
    setSelectedItem(item);
    setEditForm({ ...item });
    setShowEditModal(true);
  };

  const handleSaveEdit = async () => {
    if (!selectedItem) return;
    try {
      const updatedItems = items.map(item =>
        item.cookie_id === selectedItem.cookie_id && item.item_id === selectedItem.item_id
          ? { ...item, ...editForm }
          : item
      );
      setItems(updatedItems);
      setShowEditModal(false);
    } catch (error) {
      console.error('更新商品失败:', error);
      alert('更新失败，请重试');
    }
  };

  const handleDelete = async (item: Item) => {
    if (confirm(`确认删除商品"${item.item_title}"吗？`)) {
      try {
        const filteredItems = items.filter(i =>
          !(i.cookie_id === item.cookie_id && i.item_id === item.item_id)
        );
        setItems(filteredItems);
      } catch (error) {
        console.error('删除商品失败:', error);
        alert('删除失败，请重试');
      }
    }
  };

  const handleAddItem = async () => {
    try {
      const newItem: Item = {
        ...addForm,
        id: Date.now().toString()
      } as Item;
      setItems([newItem, ...items]);
      setShowAddModal(false);
      setAddForm({
        cookie_id: '',
        item_id: '',
        item_title: '',
        item_price: '',
        item_image: '',
        is_multi_spec: false,
        is_multi_qty_ship: false
      });
    } catch (error) {
      console.error('添加商品失败:', error);
      alert('添加失败，请重试');
    }
  };

  const toggleMultiSpec = async (item: Item) => {
    try {
      const updatedItems = items.map(i =>
        i.cookie_id === item.cookie_id && i.item_id === item.item_id
          ? { ...i, is_multi_spec: !i.is_multi_spec }
          : i
      );
      setItems(updatedItems);
    } catch (error) {
      console.error('切换状态失败:', error);
    }
  };

  const toggleMultiQty = async (item: Item) => {
    try {
      const updatedItems = items.map(i =>
        i.cookie_id === item.cookie_id && i.item_id === item.item_id
          ? { ...i, is_multi_qty_ship: !i.is_multi_qty_ship }
          : i
      );
      setItems(updatedItems);
    } catch (error) {
      console.error('切换状态失败:', error);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100">商品管理</h2>
          <p className="text-gray-500 dark:text-gray-400 mt-2 text-sm">监控并管理所有账号下的闲鱼商品。</p>
        </div>
        <div className="flex gap-3">
            <select
                className="ios-input px-4 py-3 rounded-xl text-sm"
                value={selectedAccount}
                onChange={e => setSelectedAccount(e.target.value)}
            >
                <option value="">选择账号以同步</option>
                {accounts.map(acc => (
                    <option key={acc.id} value={acc.id}>{acc.nickname}</option>
                ))}
            </select>
            <button
                onClick={handleSync}
                disabled={loading || !selectedAccount}
                className="ios-btn-primary flex items-center gap-2 px-6 py-3 rounded-2xl font-bold shadow-lg shadow-yellow-200 disabled:opacity-50"
            >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                同步商品
            </button>
            <button
              onClick={() => setShowAddModal(true)}
              className="px-5 py-3 rounded-2xl font-bold bg-gray-900 text-white hover:bg-gray-800 transition-colors flex items-center gap-2 shadow-lg"
            >
              <Plus className="w-4 h-4" />
              添加商品
            </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {items.map(item => (
              <div key={`${item.cookie_id}-${item.item_id}`} className="ios-card p-4 rounded-3xl hover:shadow-lg transition-all group relative">
                  <div className="absolute top-3 right-3 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                      <button
                        onClick={() => handleEdit(item)}
                        className="p-2 bg-white/90 backdrop-blur rounded-lg shadow-md hover:bg-[#FFE815] transition-colors"
                        title="编辑"
                      >
                        <Edit className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(item)}
                        className="p-2 bg-white/90 backdrop-blur rounded-lg shadow-md hover:bg-red-100 text-red-500 transition-colors"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                  </div>
                  <div className="aspect-square bg-gray-100 rounded-2xl mb-4 overflow-hidden relative">
                      {item.item_image ? (
                          <img src={item.item_image} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                      ) : (
                          <div className="w-full h-full flex items-center justify-center text-gray-300">
                              <Box className="w-10 h-10" />
                          </div>
                      )}
                      <div className="absolute top-2 left-2 bg-black/50 backdrop-blur-md text-white text-xs font-bold px-2 py-1 rounded-lg">
                          ¥{item.item_price}
                      </div>
                  </div>
                  <h3 className="font-bold text-gray-900 line-clamp-2 text-sm mb-2 h-10">{item.item_title}</h3>
                  <div className="flex justify-between items-center text-xs text-gray-500 mb-2">
                      <span className="bg-gray-100 px-2 py-1 rounded-md truncate max-w-[100px]">ID: {item.item_id}</span>
                  </div>
                  <div className="flex gap-2">
                      <button
                        onClick={() => toggleMultiSpec(item)}
                        className={`flex-1 text-xs font-bold px-2 py-1.5 rounded-lg transition-colors ${
                          item.is_multi_spec
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                        }`}
                      >
                        多规格
                      </button>
                      <button
                        onClick={() => toggleMultiQty(item)}
                        className={`flex-1 text-xs font-bold px-2 py-1.5 rounded-lg transition-colors ${
                          item.is_multi_qty_ship
                            ? 'bg-green-100 text-green-700'
                            : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                        }`}
                      >
                        多数量发货
                      </button>
                  </div>
              </div>
          ))}
          {items.length === 0 && (
             <div className="col-span-full py-20 text-center text-gray-400">
                 <ShoppingBag className="w-12 h-12 mx-auto mb-4 opacity-30" />
                 暂无商品数据，请选择账号进行同步
             </div>
          )}
      </div>

      {/* 添加商品弹窗 */}
      {showAddModal && createPortal(
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in">
          <div className="bg-white rounded-[2.5rem] shadow-2xl max-w-lg w-full overflow-hidden animate-scale-in">
            <div className="bg-gradient-to-r from-gray-800 to-gray-900 p-8">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-14 h-14 bg-white/20 backdrop-blur-sm rounded-2xl flex items-center justify-center">
                    <Plus className="w-7 h-7 text-white" />
                  </div>
                  <h3 className="text-2xl font-black text-white">添加商品</h3>
                </div>
                <button onClick={() => setShowAddModal(false)} className="p-3 bg-white/20 rounded-2xl hover:bg-white/30 transition-colors">
                  <X className="w-5 h-5 text-white" />
                </button>
              </div>
            </div>
            <div className="p-8 space-y-5">
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">选择账号 <span className="text-red-500">*</span></label>
                <select
                  value={addForm.cookie_id}
                  onChange={e => setAddForm({ ...addForm, cookie_id: e.target.value })}
                  className="w-full ios-input px-4 py-3 rounded-xl"
                >
                  <option value="">请选择账号</option>
                  {accounts.map(acc => (
                    <option key={acc.id} value={acc.id}>{acc.nickname || acc.id}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">商品ID <span className="text-red-500">*</span></label>
                <input
                  type="text"
                  value={addForm.item_id}
                  onChange={e => setAddForm({ ...addForm, item_id: e.target.value })}
                  placeholder="闲鱼商品ID"
                  className="w-full ios-input px-4 py-3 rounded-xl"
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">商品标题</label>
                <input
                  type="text"
                  value={addForm.item_title}
                  onChange={e => setAddForm({ ...addForm, item_title: e.target.value })}
                  placeholder="商品标题（可选）"
                  className="w-full ios-input px-4 py-3 rounded-xl"
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">商品价格</label>
                <input
                  type="text"
                  value={addForm.item_price}
                  onChange={e => setAddForm({ ...addForm, item_price: e.target.value })}
                  placeholder="如 9.9"
                  className="w-full ios-input px-4 py-3 rounded-xl"
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">商品图片URL</label>
                <input
                  type="text"
                  value={addForm.item_image}
                  onChange={e => setAddForm({ ...addForm, item_image: e.target.value })}
                  placeholder="https://..."
                  className="w-full ios-input px-4 py-3 rounded-xl"
                />
              </div>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={addForm.is_multi_spec}
                    onChange={e => setAddForm({ ...addForm, is_multi_spec: e.target.checked })}
                    className="w-4 h-4 rounded accent-[#FFE815]"
                  />
                  <span className="text-sm font-bold text-gray-700">多规格</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={addForm.is_multi_qty_ship}
                    onChange={e => setAddForm({ ...addForm, is_multi_qty_ship: e.target.checked })}
                    className="w-4 h-4 rounded accent-[#FFE815]"
                  />
                  <span className="text-sm font-bold text-gray-700">多数量发货</span>
                </label>
              </div>
            </div>
            <div className="p-8 bg-gray-50 border-t border-gray-100 flex gap-4">
              <button
                onClick={() => setShowAddModal(false)}
                className="flex-1 py-4 rounded-2xl font-bold bg-white border-2 border-gray-200 hover:bg-gray-50 text-gray-700 transition-all"
              >
                取消
              </button>
              <button
                onClick={handleAddItem}
                className="flex-1 py-4 rounded-2xl font-bold bg-gradient-to-r from-gray-800 to-gray-900 text-white hover:from-gray-700 hover:to-gray-800 transition-all flex items-center justify-center gap-2"
              >
                <Plus className="w-5 h-5" />
                添加商品
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* 编辑商品弹窗 */}
      {showEditModal && selectedItem && createPortal(
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in">
          <div className="bg-white rounded-[2.5rem] shadow-2xl max-w-lg w-full overflow-hidden animate-scale-in">
            <div className="bg-gradient-to-r from-amber-400 to-amber-500 p-8">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-14 h-14 bg-white/20 backdrop-blur-sm rounded-2xl flex items-center justify-center">
                    <Edit className="w-7 h-7 text-white" />
                  </div>
                  <h3 className="text-2xl font-black text-white">编辑商品</h3>
                </div>
                <button onClick={() => setShowEditModal(false)} className="p-3 bg-white/20 rounded-2xl hover:bg-white/30 transition-colors">
                  <X className="w-5 h-5 text-white" />
                </button>
              </div>
            </div>
            <div className="p-8 space-y-5">
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">商品标题</label>
                <input
                  type="text"
                  value={editForm.item_title || ''}
                  onChange={e => setEditForm({ ...editForm, item_title: e.target.value })}
                  className="w-full ios-input px-4 py-3 rounded-xl"
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">商品价格</label>
                <input
                  type="text"
                  value={editForm.item_price || ''}
                  onChange={e => setEditForm({ ...editForm, item_price: e.target.value })}
                  className="w-full ios-input px-4 py-3 rounded-xl"
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">商品图片URL</label>
                <input
                  type="text"
                  value={editForm.item_image || ''}
                  onChange={e => setEditForm({ ...editForm, item_image: e.target.value })}
                  className="w-full ios-input px-4 py-3 rounded-xl"
                />
              </div>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editForm.is_multi_spec || false}
                    onChange={e => setEditForm({ ...editForm, is_multi_spec: e.target.checked })}
                    className="w-4 h-4 rounded accent-[#FFE815]"
                  />
                  <span className="text-sm font-bold text-gray-700">多规格</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editForm.is_multi_qty_ship || false}
                    onChange={e => setEditForm({ ...editForm, is_multi_qty_ship: e.target.checked })}
                    className="w-4 h-4 rounded accent-[#FFE815]"
                  />
                  <span className="text-sm font-bold text-gray-700">多数量发货</span>
                </label>
              </div>
            </div>
            <div className="p-8 bg-gray-50 border-t border-gray-100 flex gap-4">
              <button
                onClick={() => setShowEditModal(false)}
                className="flex-1 py-4 rounded-2xl font-bold bg-white border-2 border-gray-200 hover:bg-gray-50 text-gray-700 transition-all"
              >
                取消
              </button>
              <button
                onClick={handleSaveEdit}
                className="flex-1 py-4 rounded-2xl font-bold bg-gradient-to-r from-amber-400 to-amber-500 text-white hover:from-amber-500 hover:to-amber-600 transition-all flex items-center justify-center gap-2"
              >
                <Save className="w-5 h-5" />
                保存修改
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
};

export default ItemList;
