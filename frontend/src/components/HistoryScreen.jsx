import { ActivityIcon, Logo } from './Icons.jsx'
import { activityLabel } from '../constants.js'
import { formatDuration } from '../lib/timing.js'

export default function HistoryScreen({ history, onBack, onView }) {
  return (
    <div className="screen screen--history">
      <header className="history-head">
        <div className="brand">
          <span className="brand__mark">
            <Logo size={26} />
          </span>
          <span className="brand__name">History</span>
        </div>
        <button type="button" className="btn btn--ghost btn--sm" onClick={onBack}>
          ← Back
        </button>
      </header>

      {history.length === 0 ? (
        <div className="empty-state">
          <span className="empty-state__icon">
            <ActivityIcon name="explore_nature" size={44} />
          </span>
          <h2 className="empty-state__title">No missions yet</h2>
          <p className="empty-state__body">
            Finished missions are saved here, on this device only. Head outside first — then come
            back and this page will fill up.
          </p>
          <button type="button" className="btn btn--primary" onClick={onBack}>
            Plan my first mission
          </button>
        </div>
      ) : (
        <ul className="history-list">
          {history.map((entry) => (
            <li key={entry.id}>
              <button type="button" className="history-item" onClick={() => onView(entry)}>
                <span className="history-item__icon">
                  <ActivityIcon name={entry.mission.activity} size={22} />
                </span>
                <span className="history-item__body">
                  <span className="history-item__title">{entry.mission.title}</span>
                  <span className="history-item__meta">
                    {new Date(entry.finishedAt).toLocaleDateString(undefined, {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                    })}
                    {' · '}
                    {activityLabel(entry.mission.activity)} · {formatDuration(entry.stats.elapsed_ms)}
                  </span>
                </span>
                <span className="history-item__score">
                  {entry.stats.completed}/{entry.stats.total_tasks}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
