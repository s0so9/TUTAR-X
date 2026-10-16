/**
 * Components Test Page
 * 
 * Temporary page for testing TUTAR X components.
 * This page demonstrates AIConfidence, MensionePickCard, LiveMatchCard, and MarketRow.
 */

import { useState } from 'react'
import AIConfidence from '../components/predictions/AIConfidence'
import MensionePickCard from '../components/predictions/MensionePickCard'
import { EmptyLiveMatchCard } from '../components/dashboard/LiveMatchCard'
import LiveMatchCard from '../components/dashboard/LiveMatchCard'
import MarketRow from '../components/predictions/MarketRow'
import './ComponentsTest.css'

export function ComponentsTest() {
  const [favorite1, setFavorite1] = useState(false)
  const [combine1, setCombine1] = useState(false)
  const [combine2, setCombine2] = useState(false)
  const [combine3, setCombine3] = useState(false)

  return (
    <div className="components-test">
      <div className="components-test__header">
        <h1>TUTAR X Component Test</h1>
        <p>Testing all FEAT-002 components</p>
      </div>

      {/* AIConfidence Tests */}
      <section className="test-section">
        <h2>AIConfidence Component</h2>
        <div className="test-grid">
          <div className="test-item">
            <h3>1/6 - Çok düşük (0.15)</h3>
            <AIConfidence confidence={0.15} />
          </div>
          <div className="test-item">
            <h3>2/6 - Düşük (0.25)</h3>
            <AIConfidence confidence={0.25} />
          </div>
          <div className="test-item">
            <h3>3/6 - Orta (0.45)</h3>
            <AIConfidence confidence={0.45} />
          </div>
          <div className="test-item">
            <h3>4/6 - İyi (0.60)</h3>
            <AIConfidence confidence={0.60} />
          </div>
          <div className="test-item">
            <h3>5/6 - Yüksek (0.82)</h3>
            <AIConfidence confidence={0.82} />
          </div>
          <div className="test-item">
            <h3>6/6 - Çok yüksek (1.0)</h3>
            <AIConfidence confidence={1.0} />
          </div>
        </div>
      </section>

      {/* MensionePickCard Test */}
      <section className="test-section">
        <h2>MensionePickCard Component</h2>
        <div className="test-grid test-grid--single">
          {/* Pending without score */}
          <MensionePickCard
            homeTeam="CÓRDOBA"
            awayTeam="TENERIFE"
            marketName="İlk Yarı 4.5+ Şut"
            outcome="Üst"
            confidence={0.78}
            realOdds={1.82}
            isFavorite={favorite1}
            onToggleFavorite={() => setFavorite1(!favorite1)}
            inCombine={combine1}
            onToggleCombine={() => setCombine1(!combine1)}
            skor={null}
            durum="pending"
          />
          
          {/* Pending with score */}
          <MensionePickCard
            homeTeam="BARCELONA"
            awayTeam="REAL MADRID"
            marketName="Maç Sonucu"
            outcome="Ev Sahibi Kazanır"
            confidence={0.85}
            realOdds={1.95}
            isFavorite={false}
            onToggleFavorite={() => {}}
            inCombine={combine2}
            onToggleCombine={() => setCombine2(!combine2)}
            skor={{ ev: 3, dep: 1 }}
            durum="pending"
          />
          
          {/* Won match */}
          <MensionePickCard
            homeTeam="LIVERPOOL"
            awayTeam="ARSENAL"
            marketName="2.5+ Gol"
            outcome="Üst"
            confidence={0.72}
            realOdds={1.65}
            isFavorite={false}
            onToggleFavorite={() => {}}
            inCombine={combine3}
            onToggleCombine={() => setCombine3(!combine3)}
            skor={{ ev: 4, dep: 2 }}
            durum="won"
          />
          
          {/* Lost match */}
          <MensionePickCard
            homeTeam="CHELSEA"
            awayTeam="MANCHESTER CITY"
            marketName="İlk Yarı 1.5+ Gol"
            outcome="Üst"
            confidence={0.68}
            realOdds={1.75}
            isFavorite={false}
            onToggleFavorite={() => {}}
            inCombine={false}
            onToggleCombine={() => {}}
            skor={{ ev: 0, dep: 1 }}
            durum="lost"
          />
        </div>
      </section>

      {/* LiveMatchCard Tests */}
      <section className="test-section">
        <h2>LiveMatchCard Component</h2>
        <div className="test-grid test-grid--compact">
          <div className="test-item">
            <h3>Live Match with Stats</h3>
            <LiveMatchCard
              homeTeam="Barcelona"
              awayTeam="Real Madrid"
              score={{ home: 2, away: 1 }}
              minute={67}
              status="live"
              liveStats={{
                shots: 15,
                shotsOnTarget: 8,
                corners: 6,
                possession: 58
              }}
            />
          </div>
          <div className="test-item">
            <h3>Live Match without Stats</h3>
            <LiveMatchCard
              homeTeam="Liverpool"
              awayTeam="Manchester City"
              score={{ home: 1, away: 1 }}
              minute={45}
              status="live"
            />
          </div>
          <div className="test-item">
            <h3>Half Time</h3>
            <LiveMatchCard
              homeTeam="Arsenal"
              awayTeam="Chelsea"
              score={{ home: 0, away: 0 }}
              minute={45}
              status="ht"
            />
          </div>
          <div className="test-item">
            <h3>Full Time</h3>
            <LiveMatchCard
              homeTeam="Bayern Munich"
              awayTeam="Dortmund"
              score={{ home: 3, away: 2 }}
              minute={90}
              status="ft"
              liveStats={{
                shots: 18,
                shotsOnTarget: 12,
                corners: 9,
                possession: 62
              }}
            />
          </div>
          <div className="test-item">
            <h3>Loading State</h3>
            <LiveMatchCard
              homeTeam=""
              awayTeam=""
              score={{ home: 0, away: 0 }}
              minute={0}
              status="live"
              isLoading={true}
            />
          </div>
          <div className="test-item">
            <h3>Empty State</h3>
            <EmptyLiveMatchCard />
          </div>
        </div>
      </section>

      {/* MarketRow Tests */}
      <section className="test-section">
        <h2>MarketRow Component</h2>
        <div className="test-grid test-grid--rows">
          <MarketRow
            marketName="İlk Yarı 0.5+ Gol"
            confidence={0.75}
            realOdds={1.45}
            inCombine={combine2}
            onToggleCombine={() => setCombine2(!combine2)}
          />
          <MarketRow
            marketName="Toplam 2.5+ Gol"
            confidence={0.68}
            realOdds={1.92}
            inCombine={combine3}
            onToggleCombine={() => setCombine3(!combine3)}
          />
          <MarketRow
            marketName="Her İki Takım da Gol Atar"
            confidence={0.82}
            realOdds={1.65}
            inCombine={false}
            onToggleCombine={() => {}}
          />
        </div>
      </section>
    </div>
  )
}
