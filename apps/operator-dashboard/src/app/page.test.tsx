import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import DashboardPage from './page';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

vi.mock('@/lib/api', () => ({
  fetchConversations: vi.fn(),
  fetchMessages: vi.fn(),
  sendMessage: vi.fn(),
  connectWebSocket: vi.fn(() => ({ close: vi.fn() })),
  patchConversation: vi.fn(),
  markConversationRead: vi.fn(),
  assignConversation: vi.fn(),
  closeConversation: vi.fn(),
  reopenConversation: vi.fn(),
  fetchTeammates: vi.fn(),
  uploadAttachment: vi.fn(),
  shareProduct: vi.fn(),
  requestRating: vi.fn(),
  fetchProducts: vi.fn(),
  sendTypingEvent: vi.fn(),
  sendMarkReadEvent: vi.fn(),
  fetchTags: vi.fn(),
  fetchConversationTags: vi.fn(),
  attachConversationTag: vi.fn(),
  detachConversationTag: vi.fn(),
  fetchConversationNotes: vi.fn(),
  createConversationNote: vi.fn(),
  fetchCustomerContext: vi.fn(),
}));

import {
  fetchConversations, fetchMessages, connectWebSocket, uploadAttachment, shareProduct,
  fetchProducts, fetchTags, fetchConversationTags, attachConversationTag,
  fetchConversationNotes, createConversationNote, fetchCustomerContext, markConversationRead,
  assignConversation, closeConversation, reopenConversation, fetchTeammates,
} from '@/lib/api';

const visitorA = { id: 'v1', name: 'سارا محمدی', email: null, mobile: '0912', created_at: '2024-01-01T00:00:00Z' };
const visitorB = { id: 'v2', name: 'علی رضایی', email: null, mobile: null, created_at: '2024-01-01T00:00:00Z' };

const convA = {
  id: 'c1', status: 'OPEN', subject: '', category: '', notes: '', rating: null,
  created_at: '2024-01-01T10:00:00Z', updated_at: '2024-01-01T10:00:00Z', unread_count: 2,
  visitor: visitorA, last_message: { content: 'سلام دنیا', message_type: 'TEXT', sender_type: 'VISITOR', created_at: '2024-01-01T10:00:00Z' },
};
const convB = {
  id: 'c2', status: 'PENDING', subject: '', category: '', notes: '', rating: null,
  created_at: '2024-01-01T09:00:00Z', updated_at: '2024-01-01T09:00:00Z', unread_count: 0,
  visitor: visitorB, last_message: { content: 'ممنون', message_type: 'TEXT', sender_type: 'VISITOR', created_at: '2024-01-01T09:00:00Z' },
};
const convClosed = {
  id: 'c3', status: 'CLOSED', subject: '', category: '', notes: '', rating: null, closed_at: '2024-01-02T00:00:00Z',
  created_at: '2024-01-01T08:00:00Z', updated_at: '2024-01-01T08:00:00Z', unread_count: 0,
  visitor: { id: 'v3', name: 'رضا کریمی', email: null, mobile: null, created_at: '2024-01-01T00:00:00Z' }, last_message: null,
};

const product = { id: 'p1', brand: 'Arom', name: 'Candle', price: '890000', old_price: null, rating: '5', reviews_count: 12, image: '' };

function setDefaultMocks() {
  vi.mocked(fetchConversations).mockResolvedValue([convA, convB]);
  vi.mocked(fetchMessages).mockResolvedValue([]);
  vi.mocked(fetchProducts).mockResolvedValue([product]);
  vi.mocked(fetchTags).mockResolvedValue([{ id: 't1', name: 'VIP', color: '' }]);
  vi.mocked(fetchConversationTags).mockResolvedValue([]);
  vi.mocked(fetchConversationNotes).mockResolvedValue([]);
  vi.mocked(fetchCustomerContext).mockResolvedValue({
    name: 'سارا محمدی', phone: '0912', location: 'تهران', customer_since: '2024-01-01T00:00:00Z',
    order_count: 3, total_spent: '2340000', score: '4.9', recent_orders: [],
  });
  vi.mocked(markConversationRead).mockResolvedValue(undefined);
  vi.mocked(fetchTeammates).mockResolvedValue([{ id: 'op1', display_name: 'همکار یک', email: 'op1@test.com' }]);
}

// jsdom doesn't implement scrollIntoView; the page calls it on every message-list update.
Element.prototype.scrollIntoView = vi.fn();

// Once a conversation is selected, its visitor name renders both in the sidebar
// list item and in the chat header, so plain getByText becomes ambiguous. The
// sidebar occurrence always renders first in document order.
async function selectConversation(name: string) {
  const matches = await screen.findAllByText(name);
  fireEvent.click(matches[0]);
}

describe('Operator dashboard — customer conversations page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.localStorage = {
      getItem: vi.fn(() => 'token'), setItem: vi.fn(), removeItem: vi.fn(),
    } as unknown as Storage;
    setDefaultMocks();
  });

  it('renders the conversation list with visitor names and last-message previews', async () => {
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByText('سارا محمدی')).toBeDefined());
    expect(screen.getByText('علی رضایی')).toBeDefined();
    expect(screen.getByText('سلام دنیا')).toBeDefined();
  });

  it('shows an unread badge only for conversations with unread_count > 0', async () => {
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByText('2')).toBeDefined());
    expect(screen.queryByText('0')).toBeNull();
  });

  it('filters the list by search text', async () => {
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByText('سارا محمدی')).toBeDefined());
    fireEvent.change(screen.getByPlaceholderText('جستجوی مشتری یا گفتگو…'), { target: { value: 'علی' } });
    expect(screen.queryByText('سارا محمدی')).toBeNull();
    expect(screen.getByText('علی رضایی')).toBeDefined();
  });

  it('filters the list by status tab', async () => {
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByText('سارا محمدی')).toBeDefined());
    fireEvent.click(screen.getByRole('button', { name: 'در انتظار' }));
    expect(screen.queryByText('سارا محمدی')).toBeNull();
    expect(screen.getByText('علی رضایی')).toBeDefined();
  });

  it('selecting a conversation loads its messages, tags, notes, customer context and connects a socket', async () => {
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByText('سارا محمدی')).toBeDefined());
    await selectConversation('سارا محمدی');
    await waitFor(() => expect(fetchMessages).toHaveBeenCalledWith('c1'));
    expect(connectWebSocket).toHaveBeenCalledWith('c1', expect.any(Function));
    expect(fetchConversationTags).toHaveBeenCalledWith('c1');
    expect(fetchConversationNotes).toHaveBeenCalledWith('c1');
    expect(fetchCustomerContext).toHaveBeenCalledWith('c1');
    expect(markConversationRead).toHaveBeenCalledWith('c1');
  });

  it('renders a product message card with brand, name and price', async () => {
    vi.mocked(fetchMessages).mockResolvedValue([
      { id: 'm1', sender_type: 'USER', content: '', message_type: 'PRODUCT', client_message_id: 'm1', created_at: '2024-01-01T10:00:00Z', seen: true, attachment_url: null,
        metadata: { brand: 'Arom', name: 'Candle', price: '890000', old_price: null, rating: '5', reviews_count: 12 } },
    ]);
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByText('سارا محمدی')).toBeDefined());
    await selectConversation('سارا محمدی');
    await waitFor(() => expect(screen.getByText('Candle')).toBeDefined());
    expect(screen.getByText('Arom')).toBeDefined();
  });

  it('renders an incoming image message with its caption', async () => {
    vi.mocked(fetchMessages).mockResolvedValue([
      { id: 'm1', sender_type: 'VISITOR', content: '', message_type: 'IMAGE', client_message_id: 'm1', created_at: '2024-01-01T10:00:00Z', seen: false,
        attachment_url: 'https://example.com/pic.png', metadata: { caption: 'این عکسه' } },
    ]);
    render(<DashboardPage />);
    await selectConversation('سارا محمدی');
    await waitFor(() => expect(screen.getByText('این عکسه')).toBeDefined());
  });

  it('renders a voice message with a play control', async () => {
    vi.mocked(fetchMessages).mockResolvedValue([
      { id: 'm1', sender_type: 'VISITOR', content: '', message_type: 'VOICE', client_message_id: 'm1', created_at: '2024-01-01T10:00:00Z', seen: false,
        attachment_url: 'https://example.com/note.webm', metadata: { duration: 12 } },
    ]);
    render(<DashboardPage />);
    await selectConversation('سارا محمدی');
    await waitFor(() => expect(screen.getByText('▶')).toBeDefined());
  });

  it('opens the product picker and shares a product', async () => {
    vi.mocked(shareProduct).mockResolvedValue({
      id: 'm2', sender_type: 'USER', content: '', message_type: 'PRODUCT', client_message_id: 'gen', created_at: new Date().toISOString(), seen: true,
      attachment_url: null, metadata: { brand: 'Arom', name: 'Candle', price: '890000' },
    });
    render(<DashboardPage />);
    await selectConversation('سارا محمدی');
    fireEvent.click(await screen.findByTitle('معرفی محصول'));
    fireEvent.click(await screen.findByText('Candle'));
    await waitFor(() => expect(shareProduct).toHaveBeenCalledWith('c1', 'p1', expect.any(String)));
  });

  it('uploads an image attachment via the file input', async () => {
    vi.mocked(uploadAttachment).mockResolvedValue({
      id: 'm3', sender_type: 'USER', content: '', message_type: 'IMAGE', client_message_id: 'gen', created_at: new Date().toISOString(), seen: true,
      attachment_url: 'https://example.com/uploaded.png', metadata: {},
    });
    const { container } = render(<DashboardPage />);
    await selectConversation('سارا محمدی');
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['abc'], 'pic.png', { type: 'image/png' });
    Object.defineProperty(fileInput, 'files', { value: [file] });
    fireEvent.change(fileInput);
    await waitFor(() => expect(uploadAttachment).toHaveBeenCalledWith('c1', file, 'IMAGE', expect.any(String)));
  });

  it('attaches a workspace tag to the selected conversation', async () => {
    vi.mocked(attachConversationTag).mockResolvedValue([{ id: 't1', name: 'VIP', color: '' }]);
    render(<DashboardPage />);
    await selectConversation('سارا محمدی');
    const tagButton = await screen.findByText('VIP');
    fireEvent.click(tagButton);
    await waitFor(() => expect(attachConversationTag).toHaveBeenCalledWith('c1', 't1'));
  });

  it('adds an operator note and renders it in the note list', async () => {
    vi.mocked(createConversationNote).mockResolvedValue({ id: 'n1', body: 'مشتری علاقه‌مند به رنگ گرم است', created_by_email: 'op@test.com', created_at: new Date().toISOString() });
    render(<DashboardPage />);
    await selectConversation('سارا محمدی');
    const textarea = await screen.findByPlaceholderText('یادداشت خصوصی درباره این مشتری…');
    fireEvent.change(textarea, { target: { value: 'مشتری علاقه‌مند به رنگ گرم است' } });
    fireEvent.click(screen.getByText('افزودن یادداشت'));
    await waitFor(() => expect(createConversationNote).toHaveBeenCalledWith('c1', 'مشتری علاقه‌مند به رنگ گرم است'));
    await waitFor(() => expect(screen.getByText('مشتری علاقه‌مند به رنگ گرم است')).toBeDefined());
  });

  it('renders the customer-context summary (phone, location, orders, spend)', async () => {
    render(<DashboardPage />);
    await selectConversation('سارا محمدی');
    await waitFor(() => expect(screen.getByText('📍 تهران')).toBeDefined());
    expect(screen.getByText('3')).toBeDefined();
  });

  it('degrades gracefully when a tenant has no customer-context data', async () => {
    vi.mocked(fetchCustomerContext).mockRejectedValue(new Error('not found'));
    render(<DashboardPage />);
    await selectConversation('سارا محمدی');
    await waitFor(() => expect(screen.getByText('یادداشت‌های اپراتور')).toBeDefined());
    expect(screen.queryByText('📍')).toBeNull();
  });

  it('mobile navigation: back button returns to the list, info button opens and closes the overlay', async () => {
    render(<DashboardPage />);
    await selectConversation('سارا محمدی');

    // Back to list (mobile-only control, always present in the DOM in jsdom)
    fireEvent.click(screen.getByText('›'));
    // Selecting again to get back into chat view for the info-overlay assertions
    await selectConversation('سارا محمدی');

    fireEvent.click(screen.getByTitle('اطلاعات مشتری'));
    const overlays = screen.getAllByText('خلاصه مشتری');
    expect(overlays.length).toBe(2); // desktop panel + mobile overlay both mounted
    expect(screen.getByText('پروفایل مشتری')).toBeDefined();

    fireEvent.click(screen.getByTitle('بازگشت'));
    await waitFor(() => expect(screen.queryByText('پروفایل مشتری')).toBeNull());
  });

  it('shows a friendly error and does not crash when the conversation list fails to load', async () => {
    vi.mocked(fetchConversations).mockRejectedValue(new Error('network error'));
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByText('Failed to load conversations')).toBeDefined());
  });

  it('deduplicates a websocket echo of a message already rendered', async () => {
    const wsCallbacks: Array<(data: unknown) => void> = [];
    vi.mocked(connectWebSocket).mockImplementation((_id: string, cb: (data: unknown) => void) => {
      wsCallbacks.push(cb);
      return { close: vi.fn() } as unknown as WebSocket;
    });
    vi.mocked(fetchMessages).mockResolvedValue([
      { id: 'm1', sender_type: 'VISITOR', content: 'پیام تکراری', message_type: 'TEXT', client_message_id: 'dup-1', created_at: '2024-01-01T10:00:00Z', seen: false, attachment_url: null, metadata: {} },
    ]);
    render(<DashboardPage />);
    await selectConversation('سارا محمدی');
    await waitFor(() => expect(screen.getByText('پیام تکراری')).toBeDefined());

    act(() => {
      wsCallbacks[0]({
        id: 'm1', sender_type: 'VISITOR', content: 'پیام تکراری', message_type: 'TEXT',
        client_message_id: 'dup-1', created_at: '2024-01-01T10:00:00Z', seen: false, attachment_url: null, metadata: {},
      });
    });
    expect(screen.getAllByText('پیام تکراری').length).toBe(1);
  });

  it('reconnects by opening a fresh socket when a different conversation is selected', async () => {
    render(<DashboardPage />);
    await selectConversation('سارا محمدی');
    await waitFor(() => expect(connectWebSocket).toHaveBeenCalledWith('c1', expect.any(Function)));
    await selectConversation('علی رضایی');
    await waitFor(() => expect(connectWebSocket).toHaveBeenCalledWith('c2', expect.any(Function)));
    expect(connectWebSocket).toHaveBeenCalledTimes(2);
  });

  it('loads teammates for the selected conversation and reassigns via the dropdown', async () => {
    vi.mocked(assignConversation).mockResolvedValue({ ...convA, assigned_to: { id: 'op1', display_name: 'همکار یک', email: 'op1@test.com' } });
    render(<DashboardPage />);
    await selectConversation('سارا محمدی');
    await waitFor(() => expect(fetchTeammates).toHaveBeenCalledWith('c1'));

    const select = await screen.findByTitle('واگذاری به همکار');
    fireEvent.change(select, { target: { value: 'op1' } });
    await waitFor(() => expect(assignConversation).toHaveBeenCalledWith('c1', 'op1'));
  });

  it('shows a reopen button for closed conversations and reopens them', async () => {
    vi.mocked(fetchConversations).mockResolvedValue([convA, convB, convClosed]);
    vi.mocked(reopenConversation).mockResolvedValue({ ...convClosed, status: 'OPEN', closed_at: null });
    render(<DashboardPage />);
    await selectConversation('رضا کریمی');
    const reopenBtn = await screen.findByText('بازگشایی');
    fireEvent.click(reopenBtn);
    await waitFor(() => expect(reopenConversation).toHaveBeenCalledWith('c3'));
    await waitFor(() => expect(screen.getByText('گفتگو دوباره باز شد')).toBeDefined());
  });

  it('shows a dismissible error toast when an action fails, instead of a blocking alert', async () => {
    vi.mocked(closeConversation).mockRejectedValue(new Error('network error'));
    render(<DashboardPage />);
    await selectConversation('سارا محمدی');
    fireEvent.click(await screen.findByText('پایان گفتگو'));
    const toastMsg = await screen.findByText('پایان گفتگو ناموفق بود');
    expect(toastMsg).toBeDefined();
    fireEvent.click(screen.getByText('✕'));
    await waitFor(() => expect(screen.queryByText('پایان گفتگو ناموفق بود')).toBeNull());
  });

  describe('voice recording', () => {
    let clock = 1_000_000;
    class FakeMediaRecorder {
      static instances: FakeMediaRecorder[] = [];
      state: 'inactive' | 'recording' = 'inactive';
      ondataavailable: ((e: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      constructor() { FakeMediaRecorder.instances.push(this); }
      start() { this.state = 'recording'; }
      stop() {
        this.state = 'inactive';
        this.ondataavailable?.({ data: new Blob(['x'], { type: 'audio/webm' }) });
        this.onstop?.();
      }
    }

    beforeEach(() => {
      clock = 1_000_000;
      vi.spyOn(Date, 'now').mockImplementation(() => clock);
      FakeMediaRecorder.instances = [];
      // @ts-expect-error test double
      global.MediaRecorder = FakeMediaRecorder;
      Object.defineProperty(navigator, 'mediaDevices', {
        value: { getUserMedia: vi.fn(() => Promise.resolve({ getTracks: () => [{ stop: vi.fn() }] })) },
        configurable: true,
      });
    });

    it('records and uploads a voice message on mic start/stop', async () => {
      vi.mocked(uploadAttachment).mockResolvedValue({
        id: 'm4', sender_type: 'USER', content: '', message_type: 'VOICE', client_message_id: 'gen',
        created_at: new Date().toISOString(), seen: true, attachment_url: 'https://example.com/v.webm', metadata: { duration: 2 },
      });
      render(<DashboardPage />);
      await selectConversation('سارا محمدی');
      const micBtn = await screen.findByTitle('پیام صوتی');
      fireEvent.click(micBtn);
      await waitFor(() => expect(FakeMediaRecorder.instances.length).toBe(1));

      clock += 1500;
      fireEvent.click(micBtn);
      await waitFor(() => expect(uploadAttachment).toHaveBeenCalledWith('c1', expect.any(File), 'VOICE', expect.any(String), { duration: '2' }));
    });

    it('cancels a recording without uploading anything', async () => {
      render(<DashboardPage />);
      await selectConversation('سارا محمدی');
      const micBtn = await screen.findByTitle('پیام صوتی');
      fireEvent.click(micBtn);
      await waitFor(() => expect(FakeMediaRecorder.instances.length).toBe(1));

      clock += 1500;
      fireEvent.click(await screen.findByTitle('لغو ضبط'));
      await new Promise((r) => setTimeout(r, 0));
      expect(uploadAttachment).not.toHaveBeenCalled();
    });

    it('shows an inline toast instead of alert() when microphone access is denied', async () => {
      Object.defineProperty(navigator, 'mediaDevices', {
        value: { getUserMedia: vi.fn(() => Promise.reject(new Error('denied'))) },
        configurable: true,
      });
      const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
      render(<DashboardPage />);
      await selectConversation('سارا محمدی');
      fireEvent.click(await screen.findByTitle('پیام صوتی'));
      await screen.findByText('برای ارسال پیام صوتی، دسترسی به میکروفون لازم است.');
      expect(alertSpy).not.toHaveBeenCalled();
    });
  });
});
