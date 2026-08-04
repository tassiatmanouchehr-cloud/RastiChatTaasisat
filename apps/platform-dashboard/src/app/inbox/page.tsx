'use client';
import { useState, useEffect, useRef } from 'react';
import { fetchPlatformInbox, fetchPlatformSupportMessages, assignTicket, replyTicket, connectSupportWebSocket, markPlatformRead } from '@/lib/api';
import { useRouter } from 'next/navigation';

interface Conversation { id: string; status: string; subject: string; unread_count?: number; }
interface Message { id: string; content: string; sender_type: string; }

export default function PlatformInboxPage() {
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [selectedConv, setSelectedConv] = useState<Conversation | null>(null);
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const wsRef = useRef<WebSocket | null>(null);
    const router = useRouter();

    const loadInbox = async () => {
        try { setConversations(await fetchPlatformInbox()); } catch (e) { /* handle */ }
    };

    useEffect(() => {
        if (!localStorage.getItem('token')) { router.push('/login'); return; }
        loadInbox();
    }, []);

    const handleSelectConv = async (conv: Conversation) => {
        setSelectedConv(conv);
        setMessages([]); 
        try {
            const history = await fetchPlatformSupportMessages(conv.id);
            setMessages(history);
            await markPlatformRead(conv.id);
            loadInbox(); // Refresh unread badges
        } catch (e) { /* handle */ }
        
        if (wsRef.current) wsRef.current.close();
        wsRef.current = connectSupportWebSocket(conv.id, (data) => {
            setMessages(prev => {
                if (prev.some(m => m.id === data.id)) return prev; // Deduplicate
                return [...prev, data];
            });
        });
    };

    const handleAssign = async () => {
        if (!selectedConv) return;
        await assignTicket(selectedConv.id);
        alert('Assigned to you!');
    };

    const handleReply = async () => {
        if (!selectedConv || !input.trim()) return;
        const clientId = 'msg_' + Date.now();
        const content = input; setInput('');
        setMessages(prev => [...prev, { id: clientId, content, sender_type: 'USER' }]);
        try { await replyTicket(selectedConv.id, content, clientId); } catch (e) { /* handle */ }
    };

    return (
        <div className="flex h-screen bg-gray-100" dir="rtl">
            <div className="w-1/3 bg-white border-l border-gray-200 overflow-y-auto">
                <div className="p-4 border-b font-bold text-indigo-600">صندوق ورودی پشتیبانی</div>
                {conversations.map(conv => (
                    <div key={conv.id} onClick={() => handleSelectConv(conv)} className={`p-4 border-b cursor-pointer hover:bg-gray-50 ${selectedConv?.id === conv.id ? 'bg-indigo-50' : ''}`}>
                        <div className="flex justify-between">
                            <span className="font-medium text-sm">{conv.subject}</span>
                            {conv.unread_count && conv.unread_count > 0 && <span className="bg-red-500 text-white text-xs rounded-full px-2">{conv.unread_count}</span>}
                        </div>
                        <div className="text-xs text-gray-500">{conv.status}</div>
                    </div>
                ))}
            </div>
            <div className="flex-1 flex flex-col">
                {selectedConv ? (
                    <>
                        <div className="p-4 bg-white border-b flex justify-between items-center">
                            <span className="font-bold text-sm">#{selectedConv.subject}</span>
                            <button onClick={handleAssign} className="text-xs bg-indigo-600 text-white px-2 py-1 rounded">تخصیص به من</button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-4 space-y-3">
                            {messages.map(msg => (
                                <div key={msg.id} className={`flex ${msg.sender_type === 'USER' ? 'justify-start' : 'justify-end'}`}>
                                    <div className={`p-3 rounded-lg max-w-xs text-sm ${msg.sender_type === 'USER' ? 'bg-indigo-600 text-white' : 'bg-gray-200'}`}>{msg.content}</div>
                                </div>
                            ))}
                        </div>
                        <div className="p-4 bg-white border-t flex">
                            <input type="text" value={input} onChange={e => setInput(e.target.value)} className="flex-1 border rounded-r p-2 text-sm" placeholder="پاسخ..." />
                            <button onClick={handleReply} className="bg-indigo-600 text-white px-4 rounded-l text-sm">ارسال</button>
                        </div>
                    </>
                ) : <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">یک تیکت را انتخاب کنید</div>}
            </div>
        </div>
    );
}
