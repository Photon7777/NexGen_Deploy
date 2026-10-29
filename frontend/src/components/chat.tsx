"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { api, json, type ChatMessage, type ChatReply } from "@/lib/api";
import { DEFAULT_PLAN_SETTINGS } from "@/lib/format";
import { ErrorNote, buttonPrimary, buttonSecondary } from "@/components/ui";

const SUGGESTIONS = ["Plan my study week", "What should I work on first?", "Quiz me on regression basics"];

export function Chat() {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [effects, setEffects] = useState<ChatReply | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<ChatMessage[]>("/chat").then(setMessages, (e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages, busy]);

  async function send(message: string) {
    const trimmed = message.trim();
    if (!trimmed || busy) return;
    const now = new Date().toISOString();
    setMessages((m) => [...(m ?? []), { role: "user", content: trimmed, created_at: now }]);
    setText("");
    setBusy(true);
    setError(null);
    setEffects(null);
    try {
      const reply = await api<ChatReply>("/chat", {
        method: "POST",
        ...json({ message: trimmed, plan_settings: DEFAULT_PLAN_SETTINGS }),
      });
      setMessages((m) => [...(m ?? []), { role: "assistant", content: reply.reply, created_at: new Date().toISOString() }]);
      setEffects(reply);
    } catch (e) {
      setError((e as Error).message);
      setMessages((m) => m?.slice(0, -1) ?? null);
      setText(trimmed);
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    try {
      await api("/chat", { method: "DELETE" });
      setMessages([]);
      setEffects(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="flex h-[calc(100dvh-11rem)] min-h-[420px] flex-col rounded-xl border border-line bg-surface">
      <div className="flex-1 space-y-4 overflow-y-auto p-4" aria-live="polite">
        {messages?.length === 0 && (
          <p className="text-sm text-muted">
            I can see your assignments. Ask me to plan your week, tell you what to tackle first, record your progress
            (&ldquo;I&apos;m halfway through the case write-up&rdquo;), or quiz you on a topic. I remember this
            conversation.
          </p>
        )}
        {messages?.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className={
                m.role === "user"
                  ? "max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-umd-red px-4 py-2 text-sm text-white"
                  : "chat-md max-w-[85%] rounded-2xl rounded-bl-sm border border-line bg-background px-4 py-2 text-sm"
              }
            >
              {m.role === "user" ? m.content : <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>}
            </div>
          </div>
        ))}
        {busy && <p className="text-sm text-muted">Thinking...</p>}
        {effects && (effects.plan_updated || effects.progress_updated.length > 0) && (
          <p className="text-xs text-muted">
            {effects.progress_updated.length > 0 && <>Updated progress: {effects.progress_updated.join(", ")}. </>}
            {effects.plan_updated && (
              <>
                Saved a new study plan. <Link href="/dashboard/plan" className="underline">See the plan</Link>
              </>
            )}
          </p>
        )}
        <div ref={end} />
      </div>

      <div className="border-t border-line p-3">
        <ErrorNote message={error} />
        <div className="mb-2 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => send(s)} disabled={busy} className={buttonSecondary}>
              {s}
            </button>
          ))}
          {messages && messages.length > 0 && (
            <button onClick={clear} disabled={busy} className="ml-auto text-xs text-muted hover:text-foreground">
              Clear conversation
            </button>
          )}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(text);
          }}
          className="flex gap-2"
        >
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(text);
              }
            }}
            rows={2}
            maxLength={2000}
            placeholder="Ask NexLearn anything"
            aria-label="Message"
            className="flex-1 resize-none rounded-md border border-line bg-background px-3 py-2 text-sm focus:border-umd-red focus:outline-none"
          />
          <button type="submit" disabled={busy || !text.trim()} className={buttonPrimary}>
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
