# Chat Message Persistence Design

## 1. Introduction

### 1.1 Problem Statement

When typing a message in the chat interface, the message content can be lost under several conditions:

1. **Background Refresh / Component Remount While Typing** - The typed content only exists in the DOM (contentEditable div) and is NOT continuously synced to React state or persisted to storage. Any component remount loses everything. This includes:
   - Query invalidation causing re-renders
   - Conversation status changes triggering remounts
   - React Strict Mode double-mount in development
   - Hot module reload during development
   - Transient timeout/reconnect cycles that cause the UI to remount

2. **Idle Conversation Resumption (Runtime Startup Gap)** - When returning to an idle conversation, the runtime may need to "awaken" before the WebSocket can connect. The gap between "user can type" and "WebSocket is ready" is critical because:
   - The UI appears ready (input is enabled, chat is visible)
   - There may be no clear indicator that the system is "waking up"
   - Users naturally start typing immediately upon returning
   - Messages submitted during this startup period are lost

3. **WebSocket Not Yet Connected** - When starting a new conversation or returning to an existing one, there is a brief period where the WebSocket connection is being established (status: CONNECTING). Messages submitted during this window are lost.

4. **WebSocket Disconnection During Use** - If the WebSocket connection drops (due to network issues, server restart, or other transient failures), messages submitted before reconnection completes are lost.

5. **Page Refresh** - If the user refreshes the page while typing a message, the draft message is lost.

**Observed User Report (OpenHands Cloud):**
- User was still writing a long prompt (had not sent it yet)
- Connection indicator was showing "ready"
- A "timeout" toast briefly appeared
- Immediately after, the prompt input box was wiped/cleared
- App showed "reconnecting", reconnection succeeded quickly
- The partially written prompt was gone

**Root Causes Identified:**

1. **No Continuous Draft Sync** - `setMessageToSend` is only called on drawer toggle, not on every keystroke. Content lives only in the DOM.

2. **Input Cleared Synchronously Before Send Confirmation** - In `use-chat-submission.ts`, input is cleared immediately after calling `onSubmit()` without waiting for confirmation.

3. **V1 sendMessage Throws Instead of Queuing** - Unlike V0 which had `pendingEventsRef`, V1 throws an error when WebSocket is not connected with no fallback queue.

4. **send() Not Awaited** - The send call is not awaited, so errors don't prevent cleanup.

This issue causes significant user frustration, especially when composing longer or more complex messages.

### 1.2 Proposed Solution

We propose a multi-layered defense-in-depth solution (combining recommended Options A + B from issue feedback):

**Layer 1: Draft Persistence** - Continuously sync the chat input content to localStorage (debounced on every keystroke) so that drafts survive component remounts, page refreshes, and transient timeout/reconnect cycles. When a user returns to a conversation, their draft is automatically restored. Drafts are keyed by conversation ID to support switching between conversations.

**Layer 2: Pending Message Queue** - When WebSocket is not connected or in a transitional state (including runtime startup), queue outgoing messages in localStorage (keyed by conversation ID). Users can submit messages even while the runtime is booting up - the messages will be processed once the runtime has started or resumed. This allows users to send a message and move on to other tasks/pages.

**Layer 3: UX Changes for Queue Support** - Enable message submission while runtime is starting:
- Allow Enter key to submit messages to the queue while runtime is booting (currently creates a new line)
- Enable the submit button (⬆️) during runtime startup (currently disabled)
- Show clear visual feedback for queued/pending message status

**Scope:** This design targets V1 conversations only. V0 already has a working `pendingEventsRef` queue mechanism in `ws-client-provider.tsx`.

**Limitations and Trade-offs:**
- localStorage is per-origin and has ~5MB limit - suitable for text but we don't persist large file attachments in drafts
- Queued messages older than 24 hours are discarded to prevent stale message delivery
- We prioritize simplicity over complex offline-first capabilities - this is not a full offline messaging solution
- Need to handle edge cases: queue size limits, stale messages, message ordering guarantees

## 2. User Interface

### 2.1 Draft Restoration Scenario

**Scenario:** User is typing a message, accidentally refreshes the page, and returns to the conversation.

**Experience:**
1. User types "Please refactor the authentication module to use..." in the chat input
2. User accidentally presses F5 or the page is remounted due to background activity (e.g., timeout toast appears)
3. Page reloads and user navigates back to the same conversation
4. The chat input is automatically populated with "Please refactor the authentication module to use..."
5. A subtle toast notification appears: "Draft restored" (dismisses after 2 seconds)
6. User continues typing and submits normally

### 2.2 Conversation Switching Scenario

**Scenario:** User is typing a message in one conversation and switches to another conversation.

**Experience:**
1. User is in Conversation A, types "Implement the login feature..."
2. User clicks on Conversation B in the sidebar
3. The chat input is cleared (Conversation A's draft is saved to localStorage)
4. If Conversation B has a saved draft, it is restored to the input
5. User switches back to Conversation A
6. The input is populated with "Implement the login feature..."

**Key Behavior:** Drafts are keyed by conversation ID. Each conversation maintains its own independent draft. Users can have unfinished drafts across multiple conversations simultaneously - switching conversations saves the current draft and restores the target conversation's draft (if any).

### 2.3 Queue Message During Runtime Startup Scenario

**Scenario:** User returns to an idle conversation and wants to submit a message while the runtime is starting.

**Experience:**
1. User navigates to an idle conversation
2. Runtime begins starting up (status shows "Starting..." or similar)
3. User types a message: "Fix the bug in the payment module"
4. User presses Enter or clicks the submit button (⬆️)
5. **NEW BEHAVIOR:** The message is accepted and queued (previously, Enter would create a new line and submit was disabled)
6. The message appears in the chat with a "Queued" indicator (clock icon)
7. The input clears, allowing the user to type additional messages or navigate away
8. User can navigate to other pages/conversations while the runtime starts
9. When runtime is ready and WebSocket connects, queued messages are sent automatically
10. The status indicator updates from "Queued" to "Delivered"

### 2.4 Queued Message While Disconnected Scenario

**Scenario:** User submits a message while WebSocket is disconnected due to network issues.

**Experience:**
1. User types a message and presses Enter
2. WebSocket is disconnected (status indicator shows "Reconnecting...")
3. The message appears in the chat with a "Queued" indicator (clock icon)
4. The input clears normally to indicate the message was accepted into the queue
5. When WebSocket reconnects, queued messages are sent automatically
6. The status indicator updates to "Delivered"
7. If delivery fails after multiple retries, the message shows an error state with a "Retry" button

### 2.5 Multiple Conversations with Queued Messages Scenario

**Scenario:** User queues messages in multiple conversations while offline, then comes back online.

**Experience:**
1. User is in Conversation A (runtime starting), types "Fix the login bug" and presses Enter
2. Message is queued for Conversation A, input clears
3. User switches to Conversation B (also starting), types "Add unit tests" and presses Enter
4. Message is queued for Conversation B, input clears
5. User switches to Conversation C and starts typing a draft (doesn't submit)
6. User goes offline or waits for runtimes to start
7. When Conversation A's runtime is ready, its queued message is sent automatically
8. When Conversation B's runtime is ready, its queued message is sent automatically
9. Conversation C's draft is preserved in the input (not queued since not submitted)

**Key Behavior:** The message queue is keyed by conversation ID. Each conversation maintains its own independent queue. Messages are processed per-conversation when that conversation's WebSocket becomes available. Users can have queued messages pending across multiple conversations simultaneously.

### 2.6 Visual Indicators

```plaintext
┌─────────────────────────────────────────────────────┐
│ Chat Message Area                                   │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │ [User Avatar] Your message here              │   │
│  │                               [✓ Delivered]  │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │ [User Avatar] Queued message                │   │
│  │                               [🕐 Queued]    │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │ [User Avatar] Sending message               │   │
│  │                               [↗️ Sending]   │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │ [User Avatar] Failed message                │   │
│  │                        [⚠️ Failed] [Retry]   │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 2.7 Input State Changes

**Current Behavior (to be changed):**
- While runtime is booting: Enter key creates new line, submit button (⬆️) is disabled
- While WebSocket is disconnected: Submit may throw error, input is cleared anyway

**New Behavior:**
- While runtime is booting: Enter key submits to queue, submit button (⬆️) is enabled
- While WebSocket is disconnected: Submit adds to queue, input clears, message shows "Queued" status
- Input is only cleared after message is successfully queued (not before)
- Draft is cleared from localStorage only after message is queued/sent

## 3. Other Context

### 3.1 Existing Infrastructure

The codebase already has several relevant mechanisms:

1. **`conversation-local-storage.ts`** - Provides `getConversationState` and `setConversationState` for persisting conversation-specific data. Already supports conversation-keyed storage.

2. **`conversation-store.ts`** - Zustand store with `messageToSend` state that partially tracks input, but:
   - Only syncs on drawer toggle, not continuously
   - Doesn't persist to localStorage/sessionStorage
   - Lost on page refresh or component remount

3. **`ws-client-provider.tsx` (V0)** - WebSocket provider with `pendingEventsRef` for queuing events during disconnection. This pattern works but is only in V0.

4. **`conversation-websocket-context.tsx` (V1)** - V1 WebSocket context that throws an error when not connected:
   ```typescript
   if (!currentSocket || currentSocket.readyState !== WebSocket.OPEN) {
     const error = "WebSocket is not connected";
     setErrorMessage(error);
     throw new Error(error);  // No fallback queue like V0
   }
   ```

5. **`use-chat-submission.ts`** - Hook handling message submission logic. Currently clears input synchronously before any send confirmation.

6. **`optimisticUserMessage` pattern** - Already exists for showing messages before server confirmation. The `removeOptimisticUserMessage()` is called when the server echoes back `UserMessageEvent`. This confirmation signal exists but is not currently used to control when input should be cleared.

### 3.2 V0 vs V1 Differences (Scope: V1 Only)

**V0 (`ws-client-provider.tsx`):**
- Has `pendingEventsRef` queue for offline messages
- Messages queued when disconnected are sent on reconnect
- Uses Socket.IO
- **Out of scope** - existing queue mechanism works

**V1 (`conversation-websocket-context.tsx`):**
- No pending queue - throws error when disconnected
- Uses native WebSocket
- **In scope** - needs queue implementation added

Both V0 and V1 benefit from draft persistence, but this design focuses on V1 where the queue is missing.

### 3.3 Debouncing Strategy

For draft persistence, we use debouncing to avoid excessive localStorage writes:
- Debounce delay: 300ms after last keystroke
- This balances responsiveness (draft is saved quickly) with performance (not writing on every character)
- On component unmount or conversation switch, immediately flush any pending debounced save

### 3.4 Existing Confirmation Pattern

There is already a pattern for knowing when a message is confirmed:
1. `setOptimisticUserMessage()` is called on submit to show the message immediately
2. `removeOptimisticUserMessage()` is called when the server echoes back the `UserMessageEvent`

This confirmation signal could be leveraged to:
- Control when the input should be cleared (Option C from issue discussion)
- However, we chose Options A+B (queue + draft) for better UX - input clears immediately since message is guaranteed queued

## 4. Technical Design

### 4.1 Draft Persistence Layer

#### 4.1.1 Storage Schema

Extend the existing `ConversationState` interface in `conversation-local-storage.ts`:

```typescript
export interface ConversationState {
  selectedTab: ConversationTab | null;
  rightPanelShown: boolean;
  unpinnedTabs: string[];
  conversationMode: ConversationMode;
  subConversationTaskId: string | null;
  // New fields for draft persistence
  draftMessage: string | null;
  draftTimestamp: number | null;
}
```

#### 4.1.2 Draft Persistence Hook

Create a new hook `useDraftPersistence` that:
1. On mount, restores draft from localStorage into the contentEditable input
2. On input change (debounced), persists the current text to localStorage
3. On successful message submission, clears the persisted draft

```typescript
// frontend/src/hooks/chat/use-draft-persistence.ts
import { useEffect, useCallback, useRef } from "react";
import { useDebouncedCallback } from "use-debounce";
import {
  getConversationState,
  setConversationState,
} from "#/utils/conversation-local-storage";

const DRAFT_DEBOUNCE_MS = 300;
const DRAFT_MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

export function useDraftPersistence(
  conversationId: string | null,
  chatInputRef: React.RefObject<HTMLDivElement | null>,
  onDraftRestored?: () => void,
) {
  const hasRestoredRef = useRef(false);

  // Debounced save to localStorage
  const saveDraft = useDebouncedCallback((text: string) => {
    if (!conversationId) return;
    
    setConversationState(conversationId, {
      draftMessage: text || null,
      draftTimestamp: text ? Date.now() : null,
    });
  }, DRAFT_DEBOUNCE_MS);

  // Restore draft on mount
  useEffect(() => {
    if (!conversationId || !chatInputRef.current || hasRestoredRef.current) {
      return;
    }

    const state = getConversationState(conversationId);
    
    // Check if draft exists and is not stale
    if (
      state.draftMessage &&
      state.draftTimestamp &&
      Date.now() - state.draftTimestamp < DRAFT_MAX_AGE_MS
    ) {
      // Only restore if input is currently empty
      if (!chatInputRef.current.innerText?.trim()) {
        chatInputRef.current.innerText = state.draftMessage;
        hasRestoredRef.current = true;
        onDraftRestored?.();
      }
    }
  }, [conversationId, chatInputRef, onDraftRestored]);

  // Handle input changes
  const handleDraftChange = useCallback(
    (text: string) => {
      saveDraft(text);
    },
    [saveDraft],
  );

  // Clear draft on submission
  const clearDraft = useCallback(() => {
    if (!conversationId) return;
    
    saveDraft.cancel();
    setConversationState(conversationId, {
      draftMessage: null,
      draftTimestamp: null,
    });
  }, [conversationId, saveDraft]);

  return {
    handleDraftChange,
    clearDraft,
  };
}
```

### 4.2 Message Queue Layer

#### 4.2.1 Queue State Management

Create a new Zustand store for managing queued messages, using localStorage for persistence:

```typescript
// frontend/src/stores/message-queue-store.ts
import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";

export type MessageStatus = "pending" | "sending" | "failed" | "delivered";

const MESSAGE_MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

export interface QueuedMessage {
  id: string;
  conversationId: string;
  content: string;
  imageUrls: string[];
  fileUrls: string[];
  timestamp: string;
  status: MessageStatus;
  retryCount: number;
  lastError?: string;
}

interface MessageQueueState {
  messages: QueuedMessage[];
}

interface MessageQueueActions {
  enqueueMessage: (message: Omit<QueuedMessage, "id" | "status" | "retryCount">) => string;
  updateMessageStatus: (id: string, status: MessageStatus, error?: string) => void;
  removeMessage: (id: string) => void;
  getMessagesForConversation: (conversationId: string) => QueuedMessage[];
  getPendingMessages: (conversationId: string) => QueuedMessage[];
  incrementRetryCount: (id: string) => void;
  clearConversationQueue: (conversationId: string) => void;
  cleanupStaleMessages: () => void;
}

type MessageQueueStore = MessageQueueState & MessageQueueActions;

export const useMessageQueueStore = create<MessageQueueStore>()(
  devtools(
    persist(
      (set, get) => ({
        messages: [],

        enqueueMessage: (message) => {
          const id = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
          const queuedMessage: QueuedMessage = {
            ...message,
            id,
            status: "pending",
            retryCount: 0,
          };
          
          set(
            (state) => ({ messages: [...state.messages, queuedMessage] }),
            false,
            "enqueueMessage",
          );
          
          return id;
        },

        updateMessageStatus: (id, status, error) =>
          set(
            (state) => ({
              messages: state.messages.map((m) =>
                m.id === id ? { ...m, status, lastError: error } : m,
              ),
            }),
            false,
            "updateMessageStatus",
          ),

        removeMessage: (id) =>
          set(
            (state) => ({
              messages: state.messages.filter((m) => m.id !== id),
            }),
            false,
            "removeMessage",
          ),

        getMessagesForConversation: (conversationId) =>
          get().messages.filter((m) => m.conversationId === conversationId),

        getPendingMessages: (conversationId) =>
          get().messages.filter(
            (m) =>
              m.conversationId === conversationId &&
              (m.status === "pending" || m.status === "failed"),
          ),

        incrementRetryCount: (id) =>
          set(
            (state) => ({
              messages: state.messages.map((m) =>
                m.id === id ? { ...m, retryCount: m.retryCount + 1 } : m,
              ),
            }),
            false,
            "incrementRetryCount",
          ),

        clearConversationQueue: (conversationId) =>
          set(
            (state) => ({
              messages: state.messages.filter(
                (m) => m.conversationId !== conversationId,
              ),
            }),
            false,
            "clearConversationQueue",
          ),

        // Remove messages older than 24 hours
        cleanupStaleMessages: () =>
          set(
            (state) => ({
              messages: state.messages.filter(
                (m) => Date.now() - new Date(m.timestamp).getTime() < MESSAGE_MAX_AGE_MS,
              ),
            }),
            false,
            "cleanupStaleMessages",
          ),
      }),
      {
        name: "message-queue-storage",
        // Uses localStorage by default (persists across browser sessions)
      },
    ),
    { name: "message-queue-store" },
  ),
);
```

#### 4.2.2 Queue Processing Hook

Create a hook that manages queue processing and retries:

```typescript
// frontend/src/hooks/chat/use-message-queue.ts
import { useEffect, useCallback, useRef } from "react";
import { useMessageQueueStore, QueuedMessage } from "#/stores/message-queue-store";
import { createChatMessage } from "#/services/chat-service";

const MAX_RETRIES = 3;
const RETRY_DELAYS = [1000, 3000, 10000]; // Exponential backoff

interface UseMessageQueueProps {
  conversationId: string | null;
  isConnected: boolean;
  send: (event: Record<string, unknown>) => void;
}

export function useMessageQueue({
  conversationId,
  isConnected,
  send,
}: UseMessageQueueProps) {
  const {
    enqueueMessage,
    updateMessageStatus,
    removeMessage,
    getPendingMessages,
    incrementRetryCount,
  } = useMessageQueueStore();
  
  const processingRef = useRef(false);
  const retryTimeoutsRef = useRef<Map<string, NodeJS.Timeout>>(new Map());

  // Process pending messages when connection becomes available
  const processQueue = useCallback(async () => {
    if (!conversationId || !isConnected || processingRef.current) {
      return;
    }

    processingRef.current = true;
    const pendingMessages = getPendingMessages(conversationId);

    for (const message of pendingMessages) {
      if (message.retryCount >= MAX_RETRIES) {
        updateMessageStatus(message.id, "failed", "Max retries exceeded");
        continue;
      }

      try {
        updateMessageStatus(message.id, "sending");
        
        const event = createChatMessage(
          message.content,
          message.imageUrls,
          message.fileUrls,
          message.timestamp,
        );
        
        send(event);
        updateMessageStatus(message.id, "delivered");
        
        // Remove from queue after successful delivery
        setTimeout(() => removeMessage(message.id), 1000);
      } catch (error) {
        incrementRetryCount(message.id);
        updateMessageStatus(
          message.id,
          "pending",
          error instanceof Error ? error.message : "Unknown error",
        );
        
        // Schedule retry with backoff
        const delay = RETRY_DELAYS[Math.min(message.retryCount, RETRY_DELAYS.length - 1)];
        const timeout = setTimeout(() => processQueue(), delay);
        retryTimeoutsRef.current.set(message.id, timeout);
      }
    }

    processingRef.current = false;
  }, [
    conversationId,
    isConnected,
    getPendingMessages,
    updateMessageStatus,
    incrementRetryCount,
    removeMessage,
    send,
  ]);

  // Trigger queue processing when connection status changes
  useEffect(() => {
    if (isConnected && conversationId) {
      processQueue();
    }
  }, [isConnected, conversationId, processQueue]);

  // Clean up retry timeouts on unmount
  useEffect(() => {
    return () => {
      retryTimeoutsRef.current.forEach((timeout) => clearTimeout(timeout));
      retryTimeoutsRef.current.clear();
    };
  }, []);

  // Submit message - either directly or via queue
  const submitMessage = useCallback(
    (content: string, imageUrls: string[], fileUrls: string[]) => {
      if (!conversationId) return null;

      const timestamp = new Date().toISOString();
      
      if (isConnected) {
        // Direct send if connected
        const event = createChatMessage(content, imageUrls, fileUrls, timestamp);
        send(event);
        return null; // No queue ID needed
      } else {
        // Queue for later
        const id = enqueueMessage({
          conversationId,
          content,
          imageUrls,
          fileUrls,
          timestamp,
        });
        return id;
      }
    },
    [conversationId, isConnected, send, enqueueMessage],
  );

  // Manual retry for failed messages
  const retryMessage = useCallback(
    (messageId: string) => {
      updateMessageStatus(messageId, "pending");
      processQueue();
    },
    [updateMessageStatus, processQueue],
  );

  return {
    submitMessage,
    retryMessage,
    processQueue,
  };
}
```

### 4.3 Integration Points

#### 4.3.1 Modify `use-chat-input-logic.ts`

Integrate draft persistence into the existing chat input logic:

```typescript
// Add to existing useChatInputLogic hook
import { useDraftPersistence } from "./use-draft-persistence";
import { useParams } from "react-router-dom";
import { displaySuccessToast } from "#/utils/custom-toast-handlers";

export const useChatInputLogic = () => {
  const chatInputRef = useRef<HTMLDivElement | null>(null);
  const { conversationId } = useParams<{ conversationId: string }>();

  // ... existing code ...

  const { handleDraftChange, clearDraft } = useDraftPersistence(
    conversationId || null,
    chatInputRef,
    () => displaySuccessToast("Draft restored"),
  );

  // Export new functions
  return {
    chatInputRef,
    messageToSend,
    checkIsContentEmpty,
    clearEmptyContentHandler,
    getCurrentMessage,
    handleDraftChange,  // NEW
    clearDraft,         // NEW
  };
};
```

#### 4.3.2 Modify `use-chat-submission.ts`

Clear draft on successful submission (after message is queued):

```typescript
export const useChatSubmission = (
  chatInputRef: React.RefObject<HTMLDivElement | null>,
  fileInputRef: React.RefObject<HTMLInputElement | null>,
  smartResize: () => void,
  onSubmit: (message: string) => void,
  resetManualResize?: () => void,
  clearDraft?: () => void,  // NEW parameter
) => {
  const handleSubmit = useCallback(() => {
    const message = chatInputRef.current?.innerText || "";
    const trimmedMessage = message.trim();

    if (!trimmedMessage) {
      return;
    }

    // onSubmit now queues the message (guaranteed to succeed)
    onSubmit(message);
    
    // Only clear after message is successfully queued
    clearDraft?.();  // Clear draft from localStorage
    clearTextContent(chatInputRef.current);  // Clear input
    clearFileInput(fileInputRef.current);

    // ... rest of existing code ...
  }, [chatInputRef, fileInputRef, smartResize, onSubmit, resetManualResize, clearDraft]);
  
  // ... rest of hook
};
```

#### 4.3.3 Modify V1 `conversation-websocket-context.tsx`

Add pending message queue to V1 WebSocket context (similar to V0's `pendingEventsRef`):

```typescript
// In ConversationWebSocketProvider
import { useMessageQueueStore } from "#/stores/message-queue-store";

// Add queue ref similar to V0
const pendingMessagesRef = useRef<QueuedMessage[]>([]);

// Modify sendMessage to queue instead of throw
const sendMessage = useCallback(async (message: V1SendMessageRequest) => {
  if (!currentSocket || currentSocket.readyState !== WebSocket.OPEN) {
    // Queue for later instead of throwing
    const queuedId = enqueueMessage({
      conversationId,
      content: message.args.content,
      imageUrls: message.args.image_urls || [],
      fileUrls: message.args.file_urls || [],
      timestamp: message.args.timestamp,
    });
    return queuedId; // Return queue ID so caller knows it was queued
  }
  
  currentSocket.send(JSON.stringify(message));
  return null; // Return null to indicate direct send
}, [currentSocket, conversationId, enqueueMessage]);

// Process queue on connection
useEffect(() => {
  if (connectionState === "OPEN" && conversationId) {
    processQueue();
  }
}, [connectionState, conversationId, processQueue]);
```

#### 4.3.4 Enable Submit During Runtime Startup

Modify the disabled state logic to allow queuing during startup:

```typescript
// In interactive-chat-box.tsx
// BEFORE:
const isDisabled =
  curAgentState === AgentState.LOADING ||
  curAgentState === AgentState.AWAITING_USER_CONFIRMATION ||
  isTaskPolling(subConversationTaskStatus);

// AFTER:
// Only disable for confirmation states, NOT for loading/startup
// Messages during startup will be queued
const isDisabled =
  curAgentState === AgentState.AWAITING_USER_CONFIRMATION ||
  isTaskPolling(subConversationTaskStatus);
```

#### 4.3.5 Modify Enter Key Behavior During Startup

In `use-chat-input-events.ts`, modify the key handler:

```typescript
// BEFORE: Enter creates newline when disabled
const handleKeyDown = (e: React.KeyboardEvent, isDisabled: boolean, handleSubmit: () => void) => {
  if (e.key === "Enter" && !e.shiftKey) {
    if (isDisabled) {
      // Creates newline (default behavior)
      return;
    }
    e.preventDefault();
    handleSubmit();
  }
};

// AFTER: Enter always submits (to queue if not connected)
const handleKeyDown = (e: React.KeyboardEvent, isDisabled: boolean, handleSubmit: () => void) => {
  if (e.key === "Enter" && !e.shiftKey) {
    // Only prevent submission for true blocking states (e.g., confirmation dialogs)
    // During startup/disconnection, allow submission to queue
    if (isDisabled) {
      return;
    }
    e.preventDefault();
    handleSubmit();
  }
};
```

Note: The `isDisabled` check remains but is now only true for blocking states like `AWAITING_USER_CONFIRMATION`, not for startup/loading states.

### 4.4 Component Updates

#### 4.4.1 Pending Message Indicator Component

```typescript
// frontend/src/components/features/chat/pending-message-indicator.tsx
import { Loader2, AlertCircle, Check } from "lucide-react";
import { MessageStatus } from "#/stores/message-queue-store";

interface PendingMessageIndicatorProps {
  status: MessageStatus;
  onRetry?: () => void;
}

export function PendingMessageIndicator({
  status,
  onRetry,
}: PendingMessageIndicatorProps) {
  switch (status) {
    case "pending":
    case "sending":
      return (
        <div className="flex items-center gap-1 text-xs text-neutral-400">
          <Loader2 className="h-3 w-3 animate-spin" />
          <span>Sending...</span>
        </div>
      );
    case "failed":
      return (
        <div className="flex items-center gap-2 text-xs text-red-400">
          <AlertCircle className="h-3 w-3" />
          <span>Failed</span>
          {onRetry && (
            <button
              onClick={onRetry}
              className="underline hover:no-underline"
            >
              Retry
            </button>
          )}
        </div>
      );
    case "delivered":
      return (
        <div className="flex items-center gap-1 text-xs text-green-400">
          <Check className="h-3 w-3" />
          <span>Delivered</span>
        </div>
      );
    default:
      return null;
  }
}
```

## 5. Implementation Plan

All changes must pass existing lints and tests. New functionality must include unit tests.

### 5.1 Draft Persistence Foundation (M1)

Implement draft persistence with localStorage integration.

**Demo:** User can type a message, refresh the page, and see their draft restored. Switching conversations saves/restores the appropriate draft.

#### 5.1.1 Storage Schema Extension
- [ ] `frontend/src/utils/conversation-local-storage.ts` - Add `draftMessage` and `draftTimestamp` to `ConversationState`
- [ ] `frontend/__tests__/conversation-local-storage.test.ts` - Add tests for new fields

#### 5.1.2 Draft Persistence Hook
- [ ] `frontend/src/hooks/chat/use-draft-persistence.ts` - New hook for draft save/restore with debounced continuous sync
- [ ] `frontend/__tests__/hooks/chat/use-draft-persistence.test.ts` - Unit tests including conversation switching scenarios

#### 5.1.3 Integration
- [ ] `frontend/src/hooks/chat/use-chat-input-logic.ts` - Integrate draft persistence
- [ ] `frontend/src/hooks/chat/use-chat-submission.ts` - Clear draft on submit (after message is queued)
- [ ] `frontend/src/hooks/chat/use-chat-input-events.ts` - Call handleDraftChange on every input event
- [ ] `frontend/__tests__/hooks/chat/use-chat-input-logic.test.ts` - Update tests

### 5.2 Message Queue Store (M2)

Implement the message queue store with localStorage persistence.

**Demo:** Messages are stored in localStorage and can be inspected via DevTools.

#### 5.2.1 Queue Store
- [ ] `frontend/src/stores/message-queue-store.ts` - Zustand store with localStorage persistence
- [ ] `frontend/__tests__/stores/message-queue-store.test.ts` - Unit tests for enqueue, status updates, retry count, stale cleanup

### 5.3 Queue Processing and V1 WebSocket Integration (M3)

Implement queue processing with retry logic and integrate with V1 WebSocket context.

**Demo:** Disconnect WebSocket, send message, reconnect - message is delivered automatically.

#### 5.3.1 Queue Processing Hook
- [ ] `frontend/src/hooks/chat/use-message-queue.ts` - Queue processing and retry logic with exponential backoff
- [ ] `frontend/__tests__/hooks/chat/use-message-queue.test.ts` - Unit tests

#### 5.3.2 V1 WebSocket Integration
- [ ] `frontend/src/contexts/conversation-websocket-context.tsx` - Modify sendMessage to queue instead of throw when disconnected
- [ ] `frontend/__tests__/contexts/conversation-websocket-context.test.tsx` - Add tests for queuing behavior

#### 5.3.3 Stale Message Cleanup
- [ ] Call `cleanupStaleMessages()` on app startup and periodically
- [ ] Add cleanup on conversation load

### 5.4 Enable Submit During Runtime Startup (M4)

Allow users to submit messages while the runtime is starting.

**Demo:** Navigate to idle conversation, type message, press Enter - message is queued and sent when runtime is ready.

#### 5.4.1 Input Behavior Changes
- [ ] `frontend/src/components/features/chat/interactive-chat-box.tsx` - Remove `AgentState.LOADING` from disabled states
- [ ] `frontend/src/hooks/chat/use-chat-input-events.ts` - Ensure Enter submits to queue during startup
- [ ] `frontend/__tests__/components/interactive-chat-box.test.tsx` - Add tests for submit during startup

#### 5.4.2 Submit Button State
- [ ] `frontend/src/components/features/chat/components/chat-input-container.tsx` - Enable submit button during runtime startup
- [ ] `frontend/__tests__/components/features/chat/chat-input-container.test.tsx` - Add tests

### 5.5 Visual Feedback (M5)

Add UI components for message status indication.

**Demo:** Users see visual indicators for queued, sending, failed, and delivered messages.

#### 5.5.1 Status Indicator Component
- [ ] `frontend/src/components/features/chat/pending-message-indicator.tsx` - Status UI with Queued/Sending/Failed/Delivered states
- [ ] `frontend/__tests__/components/features/chat/pending-message-indicator.test.tsx` - Tests

#### 5.5.2 Chat Message Integration
- [ ] `frontend/src/components/features/chat/chat-message.tsx` - Show status indicators for queued messages
- [ ] `frontend/__tests__/components/chat-message.test.tsx` - Update tests

#### 5.5.3 Optimistic Message Update
- [ ] Update optimistic user message display to show queue status
- [ ] Integrate with existing `optimisticUserMessage` pattern

### 5.6 Polish and Edge Cases (M6)

Handle edge cases and improve user experience.

**Demo:** Full end-to-end flow works smoothly with proper error handling.

#### 5.6.1 Edge Case Handling
- [ ] Handle conversation switching (save current draft, restore target draft)
- [ ] Handle stale drafts (24-hour expiry)
- [ ] Handle queue size limits (prevent unbounded growth)
- [ ] Handle stale queued messages (age-based cleanup)
- [ ] Handle message ordering guarantees (FIFO within conversation)
- [ ] Handle queue cleanup on conversation close/delete
- [ ] Flush debounced draft save on unmount/conversation switch

#### 5.6.2 Error Recovery
- [ ] Handle retry failures gracefully with user-facing retry button
- [ ] Show clear error messages for failed messages
- [ ] Allow manual retry of failed messages

#### 5.6.3 Accessibility
- [ ] Add ARIA labels to status indicators
- [ ] Ensure keyboard navigation for retry buttons
- [ ] Screen reader announcements for status changes (queued, sent, failed)

#### 5.6.4 Integration Tests (React Testing Library + MSW)

Integration tests can be written using the existing test infrastructure without Playwright:

- **React Testing Library** - Render components and simulate user interactions
- **MSW (Mock Service Worker)** - Mock WebSocket connections (already set up in `frontend/__tests__/helpers/msw-websocket-setup.ts`)
- **JSDOM localStorage** - Vitest/Jest provides localStorage mock automatically
- **Zustand store testing** - Direct store manipulation and assertions

**Test Files:**
- [ ] `frontend/__tests__/integration/draft-persistence.test.tsx`
  - Render chat input, type message, verify localStorage updated
  - Unmount/remount component, verify draft restored from localStorage
  - Switch conversation IDs, verify drafts saved/restored per conversation
  
- [ ] `frontend/__tests__/integration/message-queue.test.tsx`
  - Render with disconnected WebSocket, submit message, verify queued in store
  - Simulate WebSocket connect, verify queued message sent
  - Verify queue keyed by conversation ID (multiple conversations)
  - Test retry logic with simulated failures
  
- [ ] `frontend/__tests__/integration/submit-during-startup.test.tsx`
  - Render with runtime starting state, verify submit button enabled
  - Submit message during startup, verify queued
  - Simulate runtime ready, verify message sent

**Example Test Pattern (using existing infrastructure):**
```typescript
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { conversationWebSocketTestSetup } from "./helpers/msw-websocket-setup";

describe("Draft Persistence", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("saves draft to localStorage on input", async () => {
    const user = userEvent.setup();
    render(<ChatInputWithProviders conversationId="conv-123" />);
    
    const input = screen.getByRole("textbox");
    await user.type(input, "my draft message");
    
    // Wait for debounced save
    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem("conversation-state-conv-123") || "{}");
      expect(stored.draftMessage).toBe("my draft message");
    });
  });

  it("restores draft on remount", async () => {
    // Pre-populate localStorage
    localStorage.setItem("conversation-state-conv-123", JSON.stringify({
      draftMessage: "restored draft",
      draftTimestamp: Date.now(),
    }));
    
    render(<ChatInputWithProviders conversationId="conv-123" />);
    
    const input = screen.getByRole("textbox");
    expect(input).toHaveTextContent("restored draft");
  });
});
```
