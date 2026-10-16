/**
 * Audio Service for Event-Based Notifications
 * 
 * Provides audio feedback for match events like goals, cards, etc.
 */

export type AudioEventType = 'goal' | 'card' | 'whistle' | 'notification' | 'alert';

export interface AudioEvent {
  type: AudioEventType;
  team?: 'home' | 'away';
  volume?: number; // 0.0 to 1.0
  priority?: 'low' | 'medium' | 'high';
}

class AudioNotificationService {
  private audioContext: AudioContext | null = null;
  private isEnabled: boolean = false;
  private volume: number = 0.5;
  private audioBuffers: Map<string, AudioBuffer> = new Map();

  constructor() {
    // Initialize from localStorage
    this.isEnabled = localStorage.getItem('audioNotifications') === 'true';
    const savedVolume = localStorage.getItem('audioVolume');
    if (savedVolume) {
      this.volume = parseFloat(savedVolume);
    }
  }

  /**
   * Initialize audio context (requires user interaction)
   */
  async initialize(): Promise<void> {
    if (this.audioContext) return;

    try {
      this.audioContext = new (window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
      
      // Preload audio files
      await this.preloadAudioFiles();
      
      console.log('Audio service initialized');
    } catch (error) {
      console.warn('Failed to initialize audio context:', error);
    }
  }

  /**
   * Preload audio files for better performance
   */
  private async preloadAudioFiles(): Promise<void> {
    // In a real implementation, you would load actual audio files
    // For now, we'll generate synthetic tones
    const audioFiles: { [key: string]: () => Promise<AudioBuffer> } = {
      'goal': () => this.createGoalSound(),
      'card_yellow': () => this.createCardSound('yellow'),
      'card_red': () => this.createCardSound('red'),
      'whistle': () => this.createWhistleSound(),
      'notification': () => this.createNotificationSound(),
      'alert': () => this.createAlertSound(),
    };

    for (const [key, generator] of Object.entries(audioFiles)) {
      try {
        const buffer = await generator();
        this.audioBuffers.set(key, buffer);
      } catch (error) {
        console.warn(`Failed to create audio for ${key}:`, error);
      }
    }
  }

  /**
   * Create goal celebration sound
   */
  private async createGoalSound(): Promise<AudioBuffer> {
    if (!this.audioContext) throw new Error('Audio context not initialized');

    const buffer = this.audioContext.createBuffer(1, 44100, 44100); // 1 second
    const data = buffer.getChannelData(0);

    // Create a celebratory ascending melody
    const notes = [440, 523, 659, 784]; // A4, C5, E5, G5
    let sampleIndex = 0;

    for (let noteIndex = 0; noteIndex < notes.length; noteIndex++) {
      const frequency = notes[noteIndex];
      const noteDuration = 0.2; // 200ms per note
      const samples = Math.floor(44100 * noteDuration);

      for (let i = 0; i < samples; i++) {
        const t = i / 44100;
        const envelope = Math.exp(-t * 3); // Decay envelope
        data[sampleIndex++] = Math.sin(2 * Math.PI * frequency * t) * envelope * 0.3;
      }

      // Add small gap between notes
      const gapSamples = Math.floor(44100 * 0.05);
      for (let i = 0; i < gapSamples && sampleIndex < data.length; i++) {
        data[sampleIndex++] = 0;
      }
    }

    return buffer;
  }

  /**
   * Create card sound (different tones for yellow/red)
   */
  private async createCardSound(type: 'yellow' | 'red'): Promise<AudioBuffer> {
    if (!this.audioContext) throw new Error('Audio context not initialized');

    const buffer = this.audioContext.createBuffer(1, 22050, 44100); // 0.5 seconds
    const data = buffer.getChannelData(0);

    const frequency = type === 'yellow' ? 800 : 400; // Higher pitch for yellow, lower for red
    
    for (let i = 0; i < data.length; i++) {
      const t = i / 44100;
      const envelope = Math.exp(-t * 2);
      data[i] = Math.sin(2 * Math.PI * frequency * t) * envelope * 0.2;
    }

    return buffer;
  }

  /**
   * Create whistle sound
   */
  private async createWhistleSound(): Promise<AudioBuffer> {
    if (!this.audioContext) throw new Error('Audio context not initialized');

    const buffer = this.audioContext.createBuffer(1, 22050, 44100); // 0.5 seconds
    const data = buffer.getChannelData(0);

    for (let i = 0; i < data.length; i++) {
      const t = i / 44100;
      const envelope = t < 0.1 ? t * 10 : Math.exp(-(t - 0.1) * 5);
      data[i] = Math.sin(2 * Math.PI * 2000 * t) * envelope * 0.15;
    }

    return buffer;
  }

  /**
   * Create notification sound
   */
  private async createNotificationSound(): Promise<AudioBuffer> {
    if (!this.audioContext) throw new Error('Audio context not initialized');

    const buffer = this.audioContext.createBuffer(1, 11025, 44100); // 0.25 seconds
    const data = buffer.getChannelData(0);

    for (let i = 0; i < data.length; i++) {
      const t = i / 44100;
      const envelope = Math.exp(-t * 4);
      data[i] = Math.sin(2 * Math.PI * 600 * t) * envelope * 0.1;
    }

    return buffer;
  }

  /**
   * Create alert sound
   */
  private async createAlertSound(): Promise<AudioBuffer> {
    if (!this.audioContext) throw new Error('Audio context not initialized');

    const buffer = this.audioContext.createBuffer(1, 44100, 44100); // 1 second
    const data = buffer.getChannelData(0);

    // Alternating high-low beeps
    for (let i = 0; i < data.length; i++) {
      const t = i / 44100;
      const frequency = Math.floor(t * 4) % 2 === 0 ? 1000 : 800;
      const envelope = 0.3;
      data[i] = Math.sin(2 * Math.PI * frequency * t) * envelope;
    }

    return buffer;
  }

  /**
   * Play audio for an event
   */
  async playEvent(event: AudioEvent): Promise<void> {
    if (!this.isEnabled || !this.audioContext) return;

    try {
      // Ensure audio context is running
      if (this.audioContext.state === 'suspended') {
        await this.audioContext.resume();
      }

      let audioKey: string;
      
      switch (event.type) {
        case 'goal':
          audioKey = 'goal';
          break;
        case 'card':
          audioKey = 'card_yellow'; // Default to yellow, could be enhanced
          break;
        case 'whistle':
          audioKey = 'whistle';
          break;
        case 'notification':
          audioKey = 'notification';
          break;
        case 'alert':
          audioKey = 'alert';
          break;
        default:
          audioKey = 'notification';
      }

      const buffer = this.audioBuffers.get(audioKey);
      if (!buffer) {
        console.warn(`Audio buffer not found for: ${audioKey}`);
        return;
      }

      // Create audio source
      const source = this.audioContext.createBufferSource();
      const gainNode = this.audioContext.createGain();
      
      source.buffer = buffer;
      source.connect(gainNode);
      gainNode.connect(this.audioContext.destination);
      
      // Set volume
      const finalVolume = (event.volume ?? 1.0) * this.volume;
      gainNode.gain.value = finalVolume;
      
      // Play the sound
      source.start(0);

      console.log(`Played audio event: ${event.type} at volume ${finalVolume}`);
      
    } catch (error) {
      console.warn('Failed to play audio event:', error);
    }
  }

  /**
   * Enable/disable audio notifications
   */
  setEnabled(enabled: boolean): void {
    this.isEnabled = enabled;
    localStorage.setItem('audioNotifications', enabled.toString());
    
    if (enabled && !this.audioContext) {
      // Initialize audio context when enabling
      this.initialize();
    }
  }

  /**
   * Set volume (0.0 to 1.0)
   */
  setVolume(volume: number): void {
    this.volume = Math.max(0, Math.min(1, volume));
    localStorage.setItem('audioVolume', this.volume.toString());
  }

  /**
   * Get current settings
   */
  getSettings(): { enabled: boolean; volume: number } {
    return {
      enabled: this.isEnabled,
      volume: this.volume,
    };
  }

  /**
   * Test audio functionality
   */
  async testAudio(): Promise<void> {
    await this.playEvent({ type: 'notification', volume: 0.5 });
  }

  /**
   * Cleanup resources
   */
  dispose(): void {
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
    this.audioBuffers.clear();
  }
}

// Export singleton instance
export const audioService = new AudioNotificationService();

// Convenience functions
export const playGoal = (team?: 'home' | 'away') => 
  audioService.playEvent({ type: 'goal', team, priority: 'high' });

// The card type is accepted for API compatibility; the same card sound is used for both.
export const playCard = (team?: 'home' | 'away', cardType?: 'yellow' | 'red') => {
  void cardType;
  return audioService.playEvent({ type: 'card', team, priority: 'medium' });
};

export const playWhistle = () => 
  audioService.playEvent({ type: 'whistle', priority: 'medium' });

export const playNotification = () => 
  audioService.playEvent({ type: 'notification', priority: 'low' });

export const playAlert = () => 
  audioService.playEvent({ type: 'alert', priority: 'high' });