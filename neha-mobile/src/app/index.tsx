import React, { useEffect, useState } from 'react';
import API_URL from '../apiConfig';
import {
  Alert, View, Text, TextInput, TouchableOpacity, ScrollView,
  StyleSheet, StatusBar, KeyboardAvoidingView, Platform, Modal,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { getAccessToken, getChallenge, login, logout } from '../auth';

type Message = {
  id: string;
  text: string;
  from: 'neha' | 'user';
};

export default function HomeScreen() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      text: "Hello! I'm Neha. My systems are online. What shall we work on today?",
      from: 'neha',
    },
  ]);
  const [input, setInput] = useState('');
  const [mode, setMode] = useState('ONLINE');
  const [backendStatus, setBackendStatus] = useState('CHECKING');
  const [loginVisible, setLoginVisible] = useState(false);
  const [challengeId, setChallengeId] = useState('');
  const [challengeNumber, setChallengeNumber] = useState('');
  const [loginAnswer, setLoginAnswer] = useState('');
  const [loginError, setLoginError] = useState('');
  const [pendingMessage, setPendingMessage] = useState('');

  useEffect(() => {
    let active = true;

    const checkBackend = async () => {
      try {
        const response = await fetch(`${API_URL}/health`);
        const data = await response.json();

        if (active) {
          setBackendStatus(response.ok && data.ok ? 'AI BACKEND ONLINE' : 'BACKEND OFFLINE');
        }
      } catch {
        if (active) setBackendStatus('BACKEND OFFLINE');
      }
    };

    checkBackend();
    const timer = setInterval(checkBackend, 10000);

    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);


  async function sendMessage(override?: string) {
    const value = (override ?? input).trim();
    if (!value) return;
    const token = await getAccessToken();
    if (!token) {
      try {
        const challenge = await getChallenge();
        setChallengeId(challenge.challengeId);
        setChallengeNumber(challenge.challenge);
        setPendingMessage(value);
        setLoginAnswer('');
        setLoginError('');
        setLoginVisible(true);
      } catch (error) {
        setLoginError(error instanceof Error ? error.message : 'Login unavailable.');
        setLoginVisible(true);
      }
      return;
    }
    setMessages(old => [...old, { id: String(Date.now()), text: value, from: 'user' }]);
    setInput('');
    setMode('THINKING');
    try {
      const response = await fetch(`${API_URL}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ message: value }) });
      const data = await response.json();
      if (response.status === 401) {
        await logout();
        const challenge = await getChallenge();
        setChallengeId(challenge.challengeId);
        setChallengeNumber(challenge.challenge);
        setPendingMessage(value);
        setLoginVisible(true);
        setLoginError('Your session expired. Sign in again.');
        return;
      }
      if (!response.ok) throw new Error();
      setMessages(old => [...old, { id: String(Date.now()) + '-reply', text: String(data.reply), from: 'neha' }]);
      setMode('ONLINE');
    } catch {
      setMessages(old => [...old, { id: String(Date.now()) + '-error', text: 'Could not connect to Neha AI. Check that the API server is running.', from: 'neha' }]);
      setMode('CONNECTION ERROR');
    }
  }

  async function submitLogin() {
    try {
      await login(challengeId, loginAnswer);
      setLoginVisible(false);
      setLoginError('');
      setInput('');
      void sendMessage(pendingMessage);
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : 'Login failed.');
    }
  }

  function notice(title: string, detail: string) {
    setMode(title.toUpperCase());
    setMessages(old => [
      ...old,
      { id: `${Date.now()}-${Math.random()}`, text: detail, from: 'neha' },
    ]);
  }

  return (
    <SafeAreaView style={s.safe}>
      <StatusBar barStyle="light-content" />
      <KeyboardAvoidingView
        style={s.root}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={s.header}>
          <View style={s.avatarSmall}>
            <Text style={s.avatarLetter}>N</Text>
            <View style={s.onlineDot} />
          </View>
          <View style={s.identity}>
            <Text style={s.name}>NEHA</Text>
            <Text style={s.status}>{mode}  •  CYBERNETIC CORE</Text>
          </View>
          <TouchableOpacity
            style={s.headerBtn}
            onPress={() => Alert.alert('Owner session', 'Log out of Neha on this device?', [{ text: 'Cancel', style: 'cancel' }, { text: 'Log out', style: 'destructive', onPress: () => { void logout().then(() => notice('Logged out', 'A fresh login challenge is required before using protected features.')); } }])}
          >
            <Text style={s.headerBtnText}>⚙</Text>
          </TouchableOpacity>
        </View>

        <ScrollView
          style={s.scroll}
          contentContainerStyle={s.content}
          keyboardShouldPersistTaps="handled"
        >
          <View style={s.hero}>
            <View style={s.outerRing}>
              <View style={s.innerRing}>
                <View style={s.face}>
                  <Text style={s.hair}>⌁</Text>
                  <Text style={s.faceEyes}>◉  ◉</Text>
                  <Text style={s.faceNose}>╱</Text>
                  <Text style={s.faceMouth}>﹀</Text>
                </View>
              </View>
              <View style={s.ringDotTop} />
              <View style={s.ringDotBottom} />
            </View>
            <Text style={s.heroName}>NEHA <Text style={s.heroAccent}>AI</Text></Text>
            <Text style={s.heroSubtitle}>YOUR PERSONAL INTELLIGENCE</Text>
            <View style={s.coreBadge}>
              <View style={s.blueDot} />
              <Text style={s.coreText}>CYBERNETIC CORE • READY</Text>
            </View>
          </View>

          <View style={s.voicePanel}>
            <View style={s.panelHeading}>
              <Text style={s.panelTitle}>VOICE INTERFACE</Text>
              <Text style={s.panelTag}>STANDBY</Text>
            </View>
            <View style={s.wave}>
              {Array.from({ length: 31 }).map((_, i) => (
                <View key={i} style={[s.waveBar, { height: 5 + ((i * 13 + 7) % 28) }]} />
              ))}
            </View>
            <TouchableOpacity
              style={s.micOuter}
              onPress={() => notice('Voice demo', 'Microphone integration is not connected yet.')}
            >
              <View style={s.micInner}>
                <Text style={s.micIcon}>🎙</Text>
              </View>
            </TouchableOpacity>
            <Text style={s.voiceHint}>TAP TO ACTIVATE VOICE UI</Text>
          </View>

          <Text style={s.section}>SYSTEM MODULES</Text>
          <View style={s.grid}>
            {[
              ['⌘', 'CHAT', 'Conversation'],
              ['◉', 'STUDY', 'Learning mode'],
              ['⌕', 'SEARCH', 'Web research'],
              ['▤', 'MEMORY', 'Past context'],
              ['◷', 'PLANNER', 'Daily routine'],
              ['▦', 'TOOLS', 'Quick actions'],
            ].map(([icon, title, sub]) => (
              <TouchableOpacity
                key={title}
                style={s.module}
                onPress={() => notice(title, `${title} module is a UI placeholder. Integration comes next.`)}
              >
                <Text style={s.moduleIcon}>{icon}</Text>
                <Text style={s.moduleTitle}>{title}</Text>
                <Text style={s.moduleSub}>{sub}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={s.section}>COMMUNICATION LOG</Text>
          {messages.map(m => (
            <View key={m.id} style={[s.messageRow, m.from === 'user' && s.userRow]}>
              {m.from === 'neha' && (
                <View style={s.messageBadge}><Text style={s.badgeText}>N</Text></View>
              )}
              <View style={[s.bubble, m.from === 'user' ? s.userBubble : s.nehaBubble]}>
                {m.from === 'neha' && <Text style={s.sender}>NEHA • AI</Text>}
                <Text style={s.message}>{m.text}</Text>
              </View>
            </View>
          ))}
          <Text style={s.disclaimer}>
            {backendStatus}
          </Text>
        </ScrollView>

        <View style={s.composer}>
          <TextInput
            style={s.input}
            value={input}
            onChangeText={setInput}
            placeholder="Transmit a message..."
            placeholderTextColor="#7F91A5"
            multiline
            maxLength={2000}
          />
          <TouchableOpacity style={s.send} onPress={() => void sendMessage()}>
            <Text style={s.sendText}>➤</Text>
          </TouchableOpacity>
        </View>

        <View style={s.bottom}>
          {[
            ['◉', 'CHAT'],
            ['♫', 'VOICE'],
            ['▦', 'TOOLS'],
            ['•••', 'MORE'],
          ].map(([icon, label], i) => (
            <TouchableOpacity
              key={label}
              style={s.tab}
              onPress={() => i !== 0 && notice(label, `${label} controls will be implemented next.`)}
            >
              <Text style={[s.tabIcon, i === 0 && s.tabActive]}>{icon}</Text>
              <Text style={[s.tabLabel, i === 0 && s.tabLabelActive]}>{label}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <Modal visible={loginVisible} transparent animationType="fade" onRequestClose={() => setLoginVisible(false)}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.82)', justifyContent: 'center', padding: 24 }}>
            <View style={{ backgroundColor: '#101D2A', borderColor: '#5CBFFF', borderWidth: 1, borderRadius: 18, padding: 20 }}>
              <Text style={{ color: '#EAF6FF', fontSize: 18, fontWeight: '800' }}>NEHA OWNER LOGIN</Text>
              <Text style={{ color: '#A9DFFF', fontSize: 15, marginTop: 14 }}>Challenge: {challengeNumber || 'Unavailable'}</Text>
              <TextInput value={loginAnswer} onChangeText={setLoginAnswer} keyboardType="number-pad" placeholder="Enter response" placeholderTextColor="#7799B2" style={{ color: '#FFFFFF', borderColor: '#38546A', borderWidth: 1, borderRadius: 10, padding: 12, marginTop: 14 }} />
              {!!loginError && <Text style={{ color: '#FF9B9B', marginTop: 10 }}>{loginError}</Text>}
              <TouchableOpacity onPress={() => { void submitLogin(); }} style={{ backgroundColor: '#8DDCFF', padding: 13, borderRadius: 10, alignItems: 'center', marginTop: 16 }}>
                <Text style={{ color: '#06111C', fontWeight: '900' }}>UNLOCK</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setLoginVisible(false)} style={{ padding: 12, alignItems: 'center' }}>
                <Text style={{ color: '#A9DFFF' }}>CANCEL</Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#05080D' },
  root: { flex: 1, backgroundColor: '#05080D' },
  header: {
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 17,
    paddingVertical: 13, backgroundColor: '#0B111A',
    borderBottomWidth: 1, borderBottomColor: '#263D50',
  },
  avatarSmall: {
    width: 43, height: 43, borderRadius: 22, backgroundColor: '#152C40',
    borderWidth: 1.5, borderColor: '#8DDCFF', alignItems: 'center', justifyContent: 'center',
  },
  avatarLetter: { color: '#D9F5FF', fontSize: 22, fontWeight: '900' },
  onlineDot: {
    position: 'absolute', right: -1, bottom: 0, width: 10, height: 10,
    borderRadius: 5, backgroundColor: '#64F5C2', borderWidth: 2, borderColor: '#05080D',
  },
  identity: { flex: 1, marginLeft: 11 },
  name: { color: '#F0F7FF', fontSize: 18, fontWeight: '800', letterSpacing: 2 },
  status: { color: '#82B5D1', fontSize: 9, marginTop: 4, letterSpacing: 1 },
  headerBtn: {
    width: 40, height: 40, borderRadius: 13, borderWidth: 1,
    borderColor: '#344E62', alignItems: 'center', justifyContent: 'center',
  },
  headerBtnText: { color: '#C6E9FF', fontSize: 21 },
  scroll: { flex: 1 },
  content: { padding: 17, paddingBottom: 24 },
  hero: { alignItems: 'center', paddingTop: 17, paddingBottom: 22 },
  outerRing: {
    width: 188, height: 188, borderRadius: 94, borderWidth: 2,
    borderColor: '#5CBFFF', alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#091522',
  },
  innerRing: {
    width: 165, height: 165, borderRadius: 83, borderWidth: 1,
    borderColor: '#A8E6FF', alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#14283B',
  },
  face: {
    width: 127, height: 137, borderRadius: 62, backgroundColor: '#B6C7D1',
    borderWidth: 2, borderColor: '#E0F7FF', alignItems: 'center',
    justifyContent: 'center', overflow: 'hidden',
  },
  hair: { color: '#182533', fontSize: 56, fontWeight: '900', height: 49, marginTop: -10 },
  faceEyes: { color: '#078DFF', fontSize: 22, fontWeight: '900', textShadowColor: '#00AFFF', textShadowRadius: 12 },
  faceNose: { color: '#596D7A', fontSize: 19, marginTop: -1 },
  faceMouth: { color: '#354D60', fontSize: 22, marginTop: -8 },
  ringDotTop: {
    position: 'absolute', top: 10, right: 35, width: 9, height: 9,
    borderRadius: 5, backgroundColor: '#E7FBFF',
  },
  ringDotBottom: {
    position: 'absolute', bottom: 22, left: 15, width: 6, height: 6,
    borderRadius: 3, backgroundColor: '#61BDFF',
  },
  heroName: { color: '#F1F7FF', fontSize: 25, fontWeight: '900', letterSpacing: 5, marginTop: 15 },
  heroAccent: { color: '#79CFFF' },
  heroSubtitle: { color: '#7799B2', fontSize: 9, letterSpacing: 2, marginTop: 7 },
  coreBadge: {
    flexDirection: 'row', alignItems: 'center', marginTop: 12,
    paddingHorizontal: 13, paddingVertical: 7, borderWidth: 1,
    borderColor: '#2F5D78', borderRadius: 18, backgroundColor: '#0D1A27',
  },
  blueDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#6AD9FF', marginRight: 8 },
  coreText: { color: '#A9DFFF', fontSize: 9, letterSpacing: 1 },
  voicePanel: {
    borderWidth: 1, borderColor: '#31546D', borderRadius: 20,
    backgroundColor: '#0B131E', padding: 16, alignItems: 'center',
  },
  panelHeading: { flexDirection: 'row', width: '100%', justifyContent: 'space-between', alignItems: 'center' },
  panelTitle: { color: '#D9F1FF', fontSize: 11, fontWeight: '800', letterSpacing: 1.4 },
  panelTag: { color: '#6CD6FF', fontSize: 9, letterSpacing: 1.2 },
  wave: { height: 39, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 3, marginTop: 7 },
  waveBar: { width: 3, borderRadius: 3, backgroundColor: '#70CFFF' },
  micOuter: {
    width: 69, height: 69, borderRadius: 35, borderWidth: 2,
    borderColor: '#BDEBFF', alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#10283B', marginTop: 8,
  },
  micInner: { width: 53, height: 53, borderRadius: 27, backgroundColor: '#244C68', alignItems: 'center', justifyContent: 'center' },
  micIcon: { fontSize: 25 },
  voiceHint: { color: '#779AB5', fontSize: 9, letterSpacing: 1.5, marginTop: 10 },
  section: { color: '#88B8D2', fontSize: 10, fontWeight: '800', letterSpacing: 2, marginTop: 23, marginBottom: 12 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 10 },
  module: {
    width: '48%', minHeight: 105, borderWidth: 1, borderColor: '#2B4356',
    borderRadius: 15, backgroundColor: '#0B131D', padding: 13,
  },
  moduleIcon: { color: '#8CDBFF', fontSize: 24, marginBottom: 9 },
  moduleTitle: { color: '#EDF7FF', fontSize: 12, fontWeight: '800', letterSpacing: 1 },
  moduleSub: { color: '#7F9AAF', fontSize: 10, marginTop: 5 },
  messageRow: { flexDirection: 'row', alignItems: 'flex-end', marginBottom: 13 },
  userRow: { justifyContent: 'flex-end' },
  messageBadge: {
    width: 29, height: 29, borderRadius: 15, backgroundColor: '#193B53',
    borderWidth: 1, borderColor: '#6CCBFF', alignItems: 'center',
    justifyContent: 'center', marginRight: 8,
  },
  badgeText: { color: '#D7F5FF', fontWeight: '900' },
  bubble: { maxWidth: '85%', padding: 13, borderRadius: 15 },
  nehaBubble: { backgroundColor: '#101D2A', borderWidth: 1, borderColor: '#2E5067', borderBottomLeftRadius: 4 },
  userBubble: { backgroundColor: '#173D5A', borderWidth: 1, borderColor: '#4CA5D8', borderBottomRightRadius: 4 },
  sender: { color: '#8DDAFF', fontSize: 9, fontWeight: '800', letterSpacing: 1.2, marginBottom: 6 },
  message: { color: '#EDF6FF', fontSize: 14, lineHeight: 21 },
  disclaimer: { color: '#617C91', fontSize: 8, textAlign: 'center', letterSpacing: 1.2, marginTop: 10 },
  composer: {
    flexDirection: 'row', alignItems: 'flex-end', padding: 10,
    backgroundColor: '#0B111A', borderTopWidth: 1, borderTopColor: '#263D50',
  },
  input: {
    flex: 1, minHeight: 45, maxHeight: 100, color: '#F1F8FF',
    backgroundColor: '#111D2A', borderWidth: 1, borderColor: '#38546A',
    borderRadius: 14, paddingHorizontal: 13, paddingTop: 12, paddingBottom: 10, fontSize: 14,
  },
  send: {
    width: 45, height: 45, marginLeft: 8, borderRadius: 14,
    backgroundColor: '#235578', borderWidth: 1, borderColor: '#8CDAFF',
    alignItems: 'center', justifyContent: 'center',
  },
  sendText: { color: '#F4FCFF', fontSize: 22 },
  bottom: {
    flexDirection: 'row', justifyContent: 'space-around', paddingVertical: 9,
    backgroundColor: '#0B111A', borderTopWidth: 1, borderTopColor: '#263D50',
  },
  tab: { minWidth: 55, alignItems: 'center' },
  tabIcon: { color: '#71899E', fontSize: 20, height: 25 },
  tabActive: { color: '#8DDCFF' },
  tabLabel: { color: '#71899E', fontSize: 9, marginTop: 3, letterSpacing: 1 },
  tabLabelActive: { color: '#B9E9FF', fontWeight: '800' },
});
