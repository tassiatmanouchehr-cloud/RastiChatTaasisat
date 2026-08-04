const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080/api/v1';
const WS_BASE = process.env.NEXT_PUBLIC_WS_BASE_URL || 'ws://localhost:8080/ws';

export const login = async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}/auth/login/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
    });
    if (!res.ok) throw new Error('Login failed');
    const data = await res.json();
    localStorage.setItem('token', data.access);
    localStorage.setItem('user', JSON.stringify(data.user));
    return data;
};

export const getToken = () => localStorage.getItem('token');

export const fetchConversations = async () => {
    const res = await fetch(`${API_BASE}/conversations/customer/`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
    });
    if (!res.ok) throw new Error('Failed to fetch conversations');
    return res.json();
};

export const fetchMessages = async (convId: string) => {
    const res = await fetch(`${API_BASE}/conversations/${convId}/messages/`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
    });
    if (!res.ok) throw new Error('Failed to fetch messages');
    return res.json();
};

export const sendMessage = async (convId: string, content: string, clientId: string) => {
    const res = await fetch(`${API_BASE}/conversations/${convId}/send/`, {
        method: 'POST',
        headers: { 
            'Authorization': `Bearer ${getToken()}`,
            'Content-Type': 'application/json' 
        },
        body: JSON.stringify({ content, client_message_id: clientId })
    });
    if (!res.ok) throw new Error('Failed to send message');
    return res.json();
};

export const patchConversation = async (convId: string, patch: Record<string, string>) => {
    const res = await fetch(`${API_BASE}/conversations/customer/${convId}/`, {
        method: 'PATCH',
        headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error('Failed to update conversation');
    return res.json();
};

export const markConversationRead = async (convId: string) => {
    const res = await fetch(`${API_BASE}/conversations/customer/${convId}/mark_read/`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}` },
    });
    if (!res.ok) throw new Error('Failed to mark read');
};

export const assignConversation = async (convId: string) => {
    const res = await fetch(`${API_BASE}/conversations/customer/${convId}/assign/`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}` },
    });
    if (!res.ok) throw new Error('Failed to assign conversation');
    return res.json();
};

export const closeConversation = async (convId: string) => {
    const res = await fetch(`${API_BASE}/conversations/customer/${convId}/close/`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}` },
    });
    if (!res.ok) throw new Error('Failed to close conversation');
    return res.json();
};

export const uploadAttachment = async (convId: string, file: File, messageType: 'IMAGE' | 'VOICE', clientId: string, extra?: Record<string, string>) => {
    const form = new FormData();
    form.append('file', file);
    form.append('message_type', messageType);
    form.append('client_message_id', clientId);
    if (extra) Object.entries(extra).forEach(([k, v]) => form.append(k, v));
    const res = await fetch(`${API_BASE}/conversations/customer/${convId}/upload/`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}` },
        body: form,
    });
    if (!res.ok) throw new Error('Failed to upload attachment');
    return res.json();
};

export const shareProduct = async (convId: string, productId: string, clientId: string) => {
    const res = await fetch(`${API_BASE}/conversations/customer/${convId}/share_product/`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_id: productId, client_message_id: clientId }),
    });
    if (!res.ok) throw new Error('Failed to share product');
    return res.json();
};

export const requestRating = async (convId: string) => {
    const res = await fetch(`${API_BASE}/conversations/customer/${convId}/request_rating/`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}` },
    });
    if (!res.ok) throw new Error('Failed to request rating');
    return res.json();
};

export const fetchProducts = async () => {
    const res = await fetch(`${API_BASE}/products/`, { headers: { 'Authorization': `Bearer ${getToken()}` } });
    if (!res.ok) throw new Error('Failed to fetch products');
    return res.json();
};

export const sendTypingEvent = (ws: WebSocket | null) => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'typing' }));
};

export const sendMarkReadEvent = (ws: WebSocket | null) => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'mark_read' }));
};

export const connectWebSocket = (convId: string, onMessage: (data: any) => void) => {
    const token = getToken();
    console.log("Connecting to WS:", `${WS_BASE}/dashboard/${token}/${convId}/`);
    const ws = new WebSocket(`${WS_BASE}/dashboard/${token}/${convId}/`);
    
    ws.onopen = () => console.log("✅ Dashboard WS Connected");
    ws.onclose = (event) => console.log("❌ Dashboard WS Closed", event.code, event.reason);
    ws.onerror = (error) => console.log("⚠️ Dashboard WS Error", error);
    
    ws.onmessage = (event) => {
        console.log("📩 Dashboard WS Message", event.data);
        const data = JSON.parse(event.data);
        onMessage(data);
    };
    return ws;
};

export const fetchSupportConversations = async () => {
    const res = await fetch(`${API_BASE}/support/`, { headers: { 'Authorization': `Bearer ${getToken()}` } });
    if (!res.ok) throw new Error('Failed to fetch support tickets');
    return res.json();
};
export const createSupportRequest = async (subject: string, message: string) => {
    const res = await fetch(`${API_BASE}/support/`, {
        method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject, initial_message: message })
    });
    if (!res.ok) throw new Error('Failed to create ticket');
    return res.json();
};
export const fetchSupportMessages = async (convId: string) => {
    const res = await fetch(`${API_BASE}/support/${convId}/messages/`, { headers: { 'Authorization': `Bearer ${getToken()}` } });
    if (!res.ok) throw new Error('Failed to fetch messages');
    return res.json();
};
export const sendSupportMessage = async (convId: string, content: string, clientId: string) => {
    const res = await fetch(`${API_BASE}/support/${convId}/send_message/`, {
        method: 'POST', headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, client_message_id: clientId })
    });
    if (!res.ok) throw new Error('Failed to send message');
    return res.json();
};
export const connectSupportWebSocket = (convId: string, onMessage: (data: any) => void) => {
    const token = getToken();
    const ws = new WebSocket(`${WS_BASE}/dashboard/support/${token}/${convId}/`);
    ws.onmessage = (event) => onMessage(JSON.parse(event.data));
    return ws;
};
