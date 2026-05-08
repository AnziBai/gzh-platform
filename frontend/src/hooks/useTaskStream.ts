import { useEffect, useRef, useState } from 'react'
import type { Task } from '../api/articles'

interface UseTaskStreamOptions {
  taskId: string | null
  onComplete?: (task: Task) => void
  onError?: (task: Task) => void
}

export function useTaskStream({ taskId, onComplete, onError }: UseTaskStreamOptions) {
  const [task, setTask] = useState<Task | null>(null)
  const [logs, setLogs] = useState<string[]>([])
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!taskId) return

    setLogs([])
    setTask(null)

    const es = new EventSource(`/api/tasks/${taskId}/stream`)
    esRef.current = es

    es.onmessage = (e) => {
      try {
        const data: Task = JSON.parse(e.data)
        setTask(data)

        if (data.message) {
          setLogs((prev) => [...prev, data.message])
        }

        if (data.status === 'completed') {
          es.close()
          onComplete?.(data)
        } else if (data.status === 'failed') {
          es.close()
          onError?.(data)
        }
      } catch {
        // ignore parse errors
      }
    }

    es.onerror = () => {
      es.close()
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [taskId])

  return { task, logs }
}
