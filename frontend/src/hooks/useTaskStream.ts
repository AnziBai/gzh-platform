import { useEffect, useRef, useState } from 'react'
import type { Task } from '../api/articles'

interface UseTaskStreamOptions {
  taskId: string | null
  onComplete?: (task: Task) => void
  onError?: (task: Task) => void
}

export function useTaskStream({ taskId, onComplete, onError }: UseTaskStreamOptions) {
  const [streamState, setStreamState] = useState<{
    taskId: string | null
    task: Task | null
    logs: string[]
  }>({ taskId: null, task: null, logs: [] })
  const esRef = useRef<EventSource | null>(null)
  const onCompleteRef = useRef(onComplete)
  const onErrorRef = useRef(onError)

  useEffect(() => {
    onCompleteRef.current = onComplete
  }, [onComplete])

  useEffect(() => {
    onErrorRef.current = onError
  }, [onError])

  useEffect(() => {
    if (!taskId) return

    const es = new EventSource(`/api/tasks/${taskId}/stream`)
    esRef.current = es

    es.onmessage = (e) => {
      try {
        const data: Task = JSON.parse(e.data)
        setStreamState((prev) => ({
          taskId,
          task: data,
          logs: data.message
            ? [...(prev.taskId === taskId ? prev.logs : []), data.message]
            : prev.taskId === taskId
              ? prev.logs
              : [],
        }))

        if (data.status === 'completed') {
          es.close()
          onCompleteRef.current?.(data)
        } else if (data.status === 'failed') {
          es.close()
          onErrorRef.current?.(data)
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

  const isCurrentTask = streamState.taskId === taskId

  return {
    task: isCurrentTask ? streamState.task : null,
    logs: isCurrentTask ? streamState.logs : [],
  }
}
