interface RastiChatConfig {
    projectKey: string;
    position?: 'left' | 'right';
    primaryColor?: string;
}

class RastiChatWidget {
    private config: RastiChatConfig;
    private container: HTMLElement;
    private panel: HTMLElement;
    private launcher: HTMLElement;
    private messagesContainer: HTMLElement;
    private inputField: HTMLInputElement;
    private ws: WebSocket | null = null;
    private sessionToken: string | null = null;
    private convId: string | null = null;
    private apiBase = 'http://localhost:8080/api/v1';
    private wsBase = 'ws://localhost:8080/ws';

    constructor(config: RastiChatConfig) {
        this.config = { position: 'right', primaryColor: '#2563eb', ...config };
        this.container = document.createElement('div');
        this.container.id = 'rasti-container';
        document.body.appendChild(this.container);
        
        this.initUI();
        this.initEvents();
        this.initSession();
    }

    private initUI() {
        this.container.innerHTML = `
            <style>
                #rasti-container * { box-sizing: border-box; font-family: Tahoma, Arial, sans-serif; }
                #rasti-launcher {
                    position: fixed; bottom: 20px; ${this.config.position}: 20px;
                    width: 60px; height: 60px; background: ${this.config.primaryColor};
                    border-radius: 50%; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.2);
                    display: flex; align-items: center; justify-content: center; color: white; font-size: 24px; z-index: 9998;
                }
                #rasti-panel {
                    position: fixed; bottom: 90px; ${this.config.position}: 20px;
                    width: 350px; height: 500px; background: white; border-radius: 10px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.2); display: none; flex-direction: column; z-index: 9999; overflow: hidden;
                }
                #rasti-header { background: ${this.config.primaryColor}; color: white; padding: 15px; font-weight: bold; }
                #rasti-messages { flex: 1; padding: 15px; overflow-y: auto; background: #f9fafb; display: flex; flex-direction: column; gap: 10px; }
                .rasti-msg { padding: 8px 12px; border-radius: 8px; max-width: 80%; word-wrap: break-word; }
                .rasti-msg.visitor { background: ${this.config.primaryColor}; color: white; align-self: flex-start; }
                .rasti-msg.operator { background: #e5e7eb; color: black; align-self: flex-end; }
                #rasti-input-area { display: flex; padding: 10px; border-top: 1px solid #e5e7eb; background: white; }
                #rasti-input { flex: 1; border: 1px solid #e5e7eb; border-radius: 5px; padding: 8px; outline: none; }
                #rasti-send { background: ${this.config.primaryColor}; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; margin-right: 10px; }
            </style>
            <div id="rasti-launcher">💬</div>
            <div id="rasti-panel">
                <div id="rasti-header">پشتیبانی آنلاین</div>
                <div id="rasti-messages"></div>
                <div id="rasti-input-area">
                    <input id="rasti-input" type="text" placeholder="پیام خود را بنویسید..." />
                    <button id="rasti-send">ارسال</button>
                </div>
            </div>
        `;
        this.launcher = document.getElementById('rasti-launcher')!;
        this.panel = document.getElementById('rasti-panel')!;
        this.messagesContainer = document.getElementById('rasti-messages')!;
        this.inputField = document.getElementById('rasti-input') as HTMLInputElement;
    }

    private initEvents() {
        this.launcher.addEventListener('click', () => {
            this.panel.style.display = this.panel.style.display === 'flex' ? 'none' : 'flex';
        });
        
        document.getElementById('rasti-send')!.addEventListener('click', this.sendMessage.bind(this));
        this.inputField.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.sendMessage();
        });
    }

    private async initSession() {
        try {
            const stored = localStorage.getItem('rasti_session');
            if (stored) {
                this.sessionToken = stored;
            } else {
                const res = await fetch(`${this.apiBase}/widget/init/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ project_key: this.config.projectKey })
                });
                const data = await res.json();
                this.sessionToken = data.session_token;
                localStorage.setItem('rasti_session', this.sessionToken!);
            }
            await this.startChat();
        } catch (error) {
            console.error("RastiChat init failed", error);
        }
    }

    private async startChat() {
        try {
            const res = await fetch(`${this.apiBase}/widget/start/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_token: this.sessionToken })
            });
            const data = await res.json();
            this.convId = data.id;
            this.connectWebSocket();
        } catch (error) {
            console.error("RastiChat start failed", error);
        }
    }

    private connectWebSocket() {
        if (!this.convId || !this.sessionToken) return;
        
        this.ws = new WebSocket(`${this.wsBase}/widget/${this.sessionToken}/${this.convId}/`);
        
        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.sender_type === 'USER') {
                this.appendMessage(data.content, 'operator');
            }
        };

        this.ws.onclose = () => {
            setTimeout(() => this.connectWebSocket(), 2000); // Reconnect
        };
    }

    private sendMessage() {
        const text = this.inputField.value.trim();
        if (!text || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;

        const client_msg_id = 'msg_' + Date.now();
        this.ws.send(JSON.stringify({
            message: text,
            client_message_id: client_msg_id
        }));
        
        this.appendMessage(text, 'visitor');
        this.inputField.value = '';
    }

    private appendMessage(text: string, type: 'visitor' | 'operator') {
        const div = document.createElement('div');
        div.className = `rasti-msg ${type}`;
        div.textContent = text;
        this.messagesContainer.appendChild(div);
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }
}

window.RastiChat = {
    init: (config: RastiChatConfig) => {
        new RastiChatWidget(config);
    }
};
