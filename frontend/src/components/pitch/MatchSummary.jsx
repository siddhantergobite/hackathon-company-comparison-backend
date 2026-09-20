import { Card, ScoreRing } from '../ui';
import { asArray, flattenVal, percentScore } from '../../utils/data';

export default function MatchSummary({ pitch, pitcherName, targetName }) {
  const score = percentScore(pitch.match_score ?? 0);
  const matches = asArray(pitch.matches);

  return (
    <Card flush pad={false}>
      <div className="match-head">
        <ScoreRing value={score} size={96} stroke={9} label={`Match score ${score ?? 0} percent`} />
        <div>
          <div className="match-head__title">{score ?? 0}% match</div>
          <div className="match-head__sub">
            How well {pitcherName} lines up with what {targetName} appears to need.
          </div>
        </div>
      </div>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>{pitcherName} offer</th>
              <th>{targetName} appears to need</th>
              <th>Fit</th>
            </tr>
          </thead>
          <tbody>
            {matches.length ? (
              matches.map((m, i) => (
                <tr key={i}>
                  <td>{flattenVal(m.pitcher_offers)}</td>
                  <td>{flattenVal(m.target_needs)}</td>
                  <td className="fit-cell">{flattenVal(m.fit)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={3} className="muted">
                  No matching services were returned.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
