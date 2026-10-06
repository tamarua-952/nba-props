# Step 0 source report — github-actions

Run at 2026-10-06 01:56 UTC. 6/14 checks OK.

| Category | Source | Status | Secs | Detail |
|---|---|---|---|---|
| Game logs | NBA CDN box score JSON | FAIL | 0.1 | HTTP 403 from https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json |
| Game logs | ESPN scoreboard + summary box score | OK | 0.2 | 7 games on 2026-03-15; summary has 27 players, stats ['MIN', 'PTS', 'FG', '3PT', 'FT', 'REB'] |
| Game logs | ESPN athlete gamelog | OK | 0.1 | Jokic gamelog: 76 events, labels ['MIN', 'FG', 'FG%', '3PT', '3P%', 'FT'] |
| Game logs | Basketball-Reference player gamelog | OK | 0.2 | HTML 375 KB, ~65 game rows (rate limit: <20 req/min) |
| Schedule | NBA CDN season schedule | FAIL | 0.0 | HTTP 403 from https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json |
| Schedule | NBA CDN today's scoreboard | FAIL | 0.0 | HTTP 403 from https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json |
| Schedule | ESPN scoreboard today/tomorrow (+spreads) | OK | 0.2 | 2026-10-06: 4 games; 2026-10-07: 5 games; 3 with spread/total attached |
| Injuries | Official NBA injury report (PDF) | FAIL | 0.2 | AssertionError: no PDF links on ['https://official.nba.com/nba-injury-report-2026-27-season/', 'https://official.nba.com/nba-injury-report-2025-26-season/'] |
| Injuries | ESPN injuries JSON | OK | 0.1 | 27 teams, 92 injury entries; e.g. Aaron Wiggins: Day-To-Day |
| Injuries | ESPN injuries HTML page | FAIL | 0.0 | AssertionError: body only 2015 bytes |
| Consensus lines | The Odds API (free tier) | OK | 0.2 | /events: 46 events, cost 0 credits; event props (Boston Celtics @ Detroit Pistons): cost 2 credits, 1 books, 8 outcomes, markets ['player_points', 'player_rebounds']; used 4, remaining 496 |
| Consensus lines | ESPN core API propBets | FAIL | 0.4 | AssertionError: event 401901820 (2026-10-06): providers ['100'] have no propBets |
| Consensus lines | PrizePicks public API | FAIL | 0.2 | HTTP 403 from https://api.prizepicks.com/projections?league_id=7&per_page=250&single_stat=true |
| Consensus lines | Underdog public API | FAIL | 0.1 | HTTP 426 from https://api.underdogfantasy.com/beta/v5/over_under_lines |
