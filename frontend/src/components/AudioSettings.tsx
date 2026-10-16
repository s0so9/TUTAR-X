import { useState, useEffect } from 'react';
import { audioService } from '../services/audioService';
import './AudioSettings.css';

interface AudioSettingsProps {
  isOpen: boolean;
  onClose: () => void;
}

export function AudioSettings({ isOpen, onClose }: AudioSettingsProps) {
  const [settings, setSettings] = useState(audioService.getSettings());
  const [isInitialized, setIsInitialized] = useState(false);

  useEffect(() => {
    if (isOpen) {
      // Refresh settings when modal opens
      setSettings(audioService.getSettings());
    }
  }, [isOpen]);

  const handleEnabledChange = async (enabled: boolean) => {
    if (enabled && !isInitialized) {
      try {
        await audioService.initialize();
        setIsInitialized(true);
      } catch (error) {
        console.error('Failed to initialize audio:', error);
        return;
      }
    }

    audioService.setEnabled(enabled);
    setSettings({ ...settings, enabled });
  };

  const handleVolumeChange = (volume: number) => {
    audioService.setVolume(volume);
    setSettings({ ...settings, volume });
  };

  const handleTestAudio = async () => {
    try {
      if (!isInitialized) {
        await audioService.initialize();
        setIsInitialized(true);
      }
      await audioService.testAudio();
    } catch (error) {
      console.error('Failed to test audio:', error);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="audio-settings-overlay" onClick={onClose}>
      <div className="audio-settings-modal" onClick={e => e.stopPropagation()}>
        <div className="audio-settings-header">
          <h3>Ses Ayarları</h3>
          <button 
            className="audio-settings-close"
            onClick={onClose}
            aria-label="Kapat"
          >
            ×
          </button>
        </div>

        <div className="audio-settings-content">
          <div className="audio-settings-section">
            <label className="audio-settings-checkbox">
              <input
                type="checkbox"
                checked={settings.enabled}
                onChange={(e) => handleEnabledChange(e.target.checked)}
              />
              <span className="audio-settings-checkbox-text">
                Olay bazlı ses bildirimleri
              </span>
            </label>
            <p className="audio-settings-description">
              Gol, kart ve diğer önemli maç olaylarında ses çalar.
            </p>
          </div>

          {settings.enabled && (
            <>
              <div className="audio-settings-section">
                <label className="audio-settings-label">
                  Ses Seviyesi: {Math.round(settings.volume * 100)}%
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={settings.volume}
                  onChange={(e) => handleVolumeChange(parseFloat(e.target.value))}
                  className="audio-settings-slider"
                />
              </div>

              <div className="audio-settings-section">
                <button 
                  className="audio-settings-test-btn"
                  onClick={handleTestAudio}
                >
                  Ses Testi
                </button>
                <p className="audio-settings-test-description">
                  Ses çalışıp çalışmadığını kontrol edin.
                </p>
              </div>

              <div className="audio-settings-section">
                <h4>Ses Türleri</h4>
                <div className="audio-settings-events">
                  <div className="audio-settings-event">
                    <span>⚽ Gol</span>
                    <span className="audio-settings-event-desc">Gol atıldığında</span>
                  </div>
                  <div className="audio-settings-event">
                    <span>🟨 Sarı Kart</span>
                    <span className="audio-settings-event-desc">Sarı kart gösterildiğinde</span>
                  </div>
                  <div className="audio-settings-event">
                    <span>🟥 Kırmızı Kart</span>
                    <span className="audio-settings-event-desc">Kırmızı kart gösterildiğinde</span>
                  </div>
                  <div className="audio-settings-event">
                    <span>🎵 Düdük</span>
                    <span className="audio-settings-event-desc">Maç başı/sonu</span>
                  </div>
                  <div className="audio-settings-event">
                    <span>🔔 Bildirim</span>
                    <span className="audio-settings-event-desc">Genel olaylar</span>
                  </div>
                </div>
              </div>
            </>
          )}

          <div className="audio-settings-note">
            <strong>Not:</strong> Bu özellik tarayıcınızın ses desteği gerektirir. 
            İlk kullanımda tarayıcınız ses izni isteyebilir.
          </div>
        </div>
      </div>
    </div>
  );
}

export default AudioSettings;