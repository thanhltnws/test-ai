import { useState, useCallback } from 'react'
import type { ChatMessage } from '../types'

const STORAGE_KEY = 'ai-insight-hub-chat-sessions'
const MAX_SESSIONS = 30

export interface ChatSession {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: string
}

function loadSessions(): ChatSession[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
  } catch {
    return []
  }
}

function persist(sessions: ChatSession[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions))
}

export function useChatHistory() {
  const [sessions, setSessions] = useState<ChatSession[]>(loadSessions)

  // Creates a new session and returns its id
  const createSession = useCallback((messages: ChatMessage[]): string => {
    const firstUser = messages.find(m => m.role === 'user')
    const raw = firstUser?.content ?? 'Untitled'
    const title = raw.length > 60 ? raw.slice(0, 60) + '…' : raw
    const session: ChatSession = {
      id: crypto.randomUUID(),
      title,
      messages,
      createdAt: new Date().toISOString(),
    }
    setSessions(prev => {
      const updated = [session, ...prev].slice(0, MAX_SESSIONS)
      persist(updated)
      return updated
    })
    return session.id
  }, [])

  const updateSession = useCallback((id: string, messages: ChatMessage[]) => {
    setSessions(prev => {
      const updated = prev.map(s => s.id === id ? { ...s, messages } : s)
      persist(updated)
      return updated
    })
  }, [])

  const deleteSession = useCallback((id: string) => {
    setSessions(prev => {
      const updated = prev.filter(s => s.id !== id)
      persist(updated)
      return updated
    })
  }, [])

  return { sessions, createSession, updateSession, deleteSession }
}
