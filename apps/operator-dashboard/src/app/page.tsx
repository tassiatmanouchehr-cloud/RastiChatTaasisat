'use client';
import { useState, useEffect, useRef } from 'react';
import { fetchConversations, fetchMessages, sendMessage, connectWebSocket } from '@/lib/api';
import { useRouter } from 'next/navigation';

interface Conversation { id: string; status: string; subject: string; }
interface Message { id: string; content: string; sender_type: string; }

export default function DashboardPage() {
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [selectedConv, setSelectedConv] = useState<Conversation | null>(null);
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [error, setError] = useState('');
    const wsRef = useRef<WebSocket | null>(null);
    const router = useRouter();

    useEffect(() => {
        if (!localStorage.getItem('token')) {
            router.push('/login');
            return;
        }
        fetchConversations().then(setConversations).catch(() => setError('Failed to load conversations'));
    }, []);

    const handleSelectConv = async (conv: Conversation) => {
        setSelectedConv(conv);
        const msgs = await fetchMessages(conv.id);
        setMessages(msgs);
        
        if (wsRef.current) wsRef.current.close();
        wsRef.current = connectWebSocket(conv.id, (data) => {
            setMessages(prev => [...prev, data]);
        });
    };

    const handleSend = async () => {
        if (!selectedConv || !input.trim()) return;
        const clientId = 'msg_' + Date.now();
        const content = input;
        setInput('');
        
        // Optimistic UI
        setMessages(prev => [...prev, { id: clientId, content, sender_type: 'USER' }]);
        
        try {
            await sendMessage(selectedConv.id, content, clientId);
        } catch {
            setError('Failed to send');
        }
    };

    if (error) return <div className="p-4 text-red-500" dir="rtl">{error}</div>;

    return (
        <div className="flex h-screen bg-gray-100" dir="rtl">
            {/* Sidebar / Inbox */}
            <div className="w-1/3 bg-white border-l border-gray-200 overflow-y-auto">
                <div className="p-4 border-b border-gray-200 font-bold">گفتگوهای مشتریان</div>
                {conversations.map(conv => (
                    <div key={conv.id} onClick={() => handleSelectConv(conv)} 
                         className={`p-4 border-b cursor-pointer hover:bg-gray-50 ${selectedConv?.id === conv.id ? 'bg-blue-50' : ''}`}>
                        <div className="font-medium">{conv.subject || 'گفتگوی مشتری'}</div>
                        <div className="text-sm text-gray-500">{conv.status}</div>
                    </div>
                ))}
            </div>

            {/* Chat Area */}
            <div className="flex-1 flex flex-col">
                {selectedConv ? (
                    <>
                        <div className="p-4 bg-white border-b border-gray-200 font-bold">#{selectedConv.id.substring(0,8)}</div>
                        <div className="flex-1 overflow-y-auto p-4 space-y-3">
                            {messages.map(msg => (
                                <div key={msg.id} className={`flex ${msg.sender_type === 'USER' ? 'justify-start' : 'justify-end'}`}>
                                    <div className={`p-3 rounded-lg max-w-xs ${msg.sender_type === 'USER' ? 'bg-blue-600 text-white' : 'bg-gray-200'}`}>
                                        {msg.content}
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="p-4 bg-white border-t border-gray-200 flex">
                            <input type="text" value={input} onChange={(e) => setInput(e.target.value)} 
                                   className="flex-1 border rounded-r p-2" placeholder="پاسخ..." />
                            <button onClick={handleSend} className="bg-blue-600 text-white px-4 rounded-l">ارسال</button>
                        </div>
                    </>
                ) : (
                    <div className="flex-1 flex items-center justify-center text-gray-400">یک گفتگو را انتخاب کنید</div>
                )}
            </div>
        </div>
    );
}
