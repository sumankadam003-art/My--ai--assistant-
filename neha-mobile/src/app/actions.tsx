import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, Alert, SafeAreaView, ScrollView, StyleSheet,
  Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import * as SecureStore from 'expo-secure-store';
import API_URL from '../apiConfig';

type ActionItem = {
  name: string;
  description: string;
  risk: string;
  required_permissions: string[];
  requires_approval: boolean;
  enabled: boolean;
};

const TOKEN_KEY = 'neha_owner_session';
const RECOVERY_KEY = 'neha_owner_biometric_recovery_v1';
const RECOVERY_OPTIONS: SecureStore.SecureStoreOptions = {
  requireAuthentication: true,
  authenticationPrompt: 'Verify your Android biometric to access Neha password recovery',
};

export default function ActionsScreen() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');
  const [token, setToken] = useState<string | null>(null);
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('Owner login is required to control device actions.');

  const loadActions = useCallback(async (session: string) => {
    if (!API_URL) throw new Error('API address is not configured.');
    const response = await fetch(`${API_URL}/actions`, {
      headers: { Authorization: `Bearer ${session}` },
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || 'Could not load actions.');
    setActions(Array.isArray(data.actions) ? data.actions : []);
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      const saved = await SecureStore.getItemAsync(TOKEN_KEY);
      if (!saved) return;
      try {
        await loadActions(saved);
        if (active) {
          setToken(saved);
          setMessage('Owner session active. Choose an action to review.');
        }
      } catch {
        await SecureStore.deleteItemAsync(TOKEN_KEY);
      }
    })();
    return () => { active = false; };
  }, [loadActions]);

  async function signIn() {
    if (!API_URL) {
      setMessage('API address is not configured.');
      return;
    }
    if (!username.trim() || !password) {
      setMessage('Enter your Neha owner username and password.');
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(`${API_URL}/owner/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      const data = await response.json();
      if (!response.ok || !data.success || !data.access_token) {
        throw new Error(data.error || 'Owner login failed.');
      }
      await loadActions(data.access_token);
      await SecureStore.setItemAsync(TOKEN_KEY, data.access_token);
      setToken(data.access_token);
      setPassword('');
      setMessage('Owner session active. Choose an action to review.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Owner login failed.');
    } finally {
      setBusy(false);
    }
  }

  async function enableBiometricRecovery() {
    if (!token || !API_URL) return;
    setBusy(true);
    try {
      if (!SecureStore.canUseBiometricAuthentication()) {
        throw new Error('This Android device has no enrolled biometric method supported for protected recovery.');
      }
      const preparedResponse = await fetch(`${API_URL}/owner/recovery/enroll`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({}),
      });
      const prepared = await preparedResponse.json();
      if (!preparedResponse.ok || !prepared.success || !prepared.recovery_secret) {
        throw new Error(prepared.error || 'Could not prepare biometric recovery.');
      }

      await SecureStore.setItemAsync(RECOVERY_KEY, prepared.recovery_secret, RECOVERY_OPTIONS);

      const activatedResponse = await fetch(`${API_URL}/owner/recovery/activate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ recovery_secret: prepared.recovery_secret }),
      });
      const activated = await activatedResponse.json();
      if (!activatedResponse.ok || !activated.success) {
        throw new Error(activated.error || 'Recovery was stored but could not be activated. Retry setup while logged in.');
      }
      setMessage('Biometric password recovery is enabled on this Android device.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Biometric recovery setup failed.');
    } finally {
      setBusy(false);
    }
  }

  async function resetPasswordWithBiometric() {
    if (!API_URL) {
      setMessage('API address is not configured.');
      return;
    }
    if (newPassword.length < 12 || newPassword.length > 1024) {
      setMessage('New password must contain 12 to 1024 characters.');
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setMessage('The new passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      // Reading this item invokes Android's biometric-protected Keystore operation.
      const recoverySecret = await SecureStore.getItemAsync(RECOVERY_KEY, RECOVERY_OPTIONS);
      if (!recoverySecret) {
        throw new Error('Biometric recovery is not enrolled on this device. Log in with your current password and enable it first.');
      }
      const response = await fetch(`${API_URL}/owner/password/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recovery_secret: recoverySecret, new_password: newPassword }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || 'Password reset failed.');
      await SecureStore.deleteItemAsync(TOKEN_KEY);
      setToken(null);
      setActions([]);
      setPassword('');
      setNewPassword('');
      setConfirmNewPassword('');
      setMessage('Password changed successfully. Sign in using your new password.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Biometric password reset failed.');
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    if (token && API_URL) {
      try {
        await fetch(`${API_URL}/owner/logout`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({}),
        });
      } catch {
        // Local token is still removed even if the API is unavailable.
      }
    }
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    setToken(null);
    setActions([]);
    setMessage('Signed out. Device actions are locked.');
  }

  async function approveAndRun(action: ActionItem) {
    if (!token || !API_URL) return;
    setBusy(true);
    try {
      const approvalResponse = await fetch(`${API_URL}/actions/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          action: action.name,
          arguments: {},
          owner_confirmed: true,
        }),
      });
      const approval = await approvalResponse.json();
      if (!approvalResponse.ok || !approval.success || !approval.approval_token) {
        throw new Error(approval.error || 'Owner approval could not be issued.');
      }

      const executionResponse = await fetch(`${API_URL}/actions/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          action: action.name,
          arguments: {},
          approval_token: approval.approval_token,
        }),
      });
      const result = await executionResponse.json();
      if (!executionResponse.ok) throw new Error(result.error || 'Action request failed.');
      const detail = result.status === 'executed_unverified'
        ? `${result.message} The handler returned; the physical result was not independently verified.`
        : result.message || result.status || 'No result was returned.';
      setMessage(`${action.description}: ${detail}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Action failed.');
      if (error instanceof Error && /session|owner/i.test(error.message)) {
        await signOut();
      }
    } finally {
      setBusy(false);
    }
  }

  function confirmAction(action: ActionItem) {
    Alert.alert(
      'Confirm device action',
      `Neha is requesting permission to: ${action.description}\n\nPermission: ${action.required_permissions.join(', ')}\nRisk: ${action.risk.toUpperCase()}\n\nDo you want to run it now?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Approve & Run', onPress: () => { void approveAndRun(action); } },
      ],
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.container}>
        <Text style={s.title}>NEHA ACTION CONTROL</Text>
        <Text style={s.subtitle}>Owner-approved Android actions</Text>
        <View style={s.statusCard}>
          <Text style={s.statusTitle}>{token ? 'OWNER SESSION ACTIVE' : 'OWNER LOGIN REQUIRED'}</Text>
          <Text style={s.statusText}>{message}</Text>
        </View>

        {!token ? (
          <>
            <View style={s.card}>
              <Text style={s.label}>OWNER USERNAME</Text>
              <TextInput
                style={s.input}
                value={username}
                onChangeText={setUsername}
                autoCapitalize="none"
                autoCorrect={false}
                placeholder="Neha owner username"
                placeholderTextColor="#8294A8"
              />
              <Text style={s.label}>NEHA-ONLY PASSWORD</Text>
              <TextInput
                style={s.input}
                value={password}
                onChangeText={setPassword}
                secureTextEntry
                placeholder="Password"
                placeholderTextColor="#8294A8"
              />
              <TouchableOpacity style={s.primary} onPress={signIn} disabled={busy}>
                {busy ? <ActivityIndicator color="#06111C" /> : <Text style={s.primaryText}>OWNER LOGIN</Text>}
              </TouchableOpacity>
              <Text style={s.hint}>This owner password is separate from your Supabase account.</Text>
            </View>
            <View style={s.card}>
              <Text style={s.section}>FORGOT OWNER PASSWORD?</Text>
              <Text style={s.hint}>If biometric recovery was enabled earlier on this Android device, verify your fingerprint to set a new password. Your fingerprint is checked by Android and is never sent to Neha's API.</Text>
              <Text style={s.label}>NEW PASSWORD</Text>
              <TextInput
                style={s.input}
                value={newPassword}
                onChangeText={setNewPassword}
                secureTextEntry
                placeholder="At least 12 characters"
                placeholderTextColor="#8294A8"
              />
              <Text style={s.label}>CONFIRM NEW PASSWORD</Text>
              <TextInput
                style={s.input}
                value={confirmNewPassword}
                onChangeText={setConfirmNewPassword}
                secureTextEntry
                placeholder="Enter it again"
                placeholderTextColor="#8294A8"
              />
              <TouchableOpacity style={s.primary} onPress={resetPasswordWithBiometric} disabled={busy}>
                {busy ? <ActivityIndicator color="#06111C" /> : <Text style={s.primaryText}>VERIFY BIOMETRIC & RESET</Text>}
              </TouchableOpacity>
            </View>
          </>
        ) : (
          <>
            <View style={s.row}>
              <Text style={s.section}>AVAILABLE ACTIONS</Text>
              <TouchableOpacity onPress={signOut}><Text style={s.logout}>LOG OUT</Text></TouchableOpacity>
            </View>
            <View style={s.card}>
              <Text style={s.section}>ACCOUNT RECOVERY</Text>
              <Text style={s.hint}>Enable this once while logged in. Android protects a random recovery credential with its biometric system. Neha receives only the credential after Android approves access, never your fingerprint.</Text>
              <TouchableOpacity style={s.secondary} onPress={enableBiometricRecovery} disabled={busy}>
                <Text style={s.secondaryText}>ENABLE BIOMETRIC PASSWORD RESET</Text>
              </TouchableOpacity>
            </View>
            {actions.map(action => (
              <View key={action.name} style={s.actionCard}>
                <View style={s.actionHeading}>
                  <Text style={s.actionName}>{action.description}</Text>
                  <Text style={s.risk}>{action.risk.toUpperCase()}</Text>
                </View>
                <Text style={s.permission}>Permission: {action.required_permissions.join(', ')}</Text>
                <TouchableOpacity
                  style={[s.primary, !action.enabled && s.disabled]}
                  disabled={busy || !action.enabled}
                  onPress={() => confirmAction(action)}
                >
                  <Text style={s.primaryText}>{action.enabled ? 'REVIEW & APPROVE' : 'DISABLED'}</Text>
                </TouchableOpacity>
              </View>
            ))}
            {actions.length === 0 && <Text style={s.hint}>No actions are registered by the API.</Text>}
          </>
        )}
        {busy && <ActivityIndicator style={s.loader} color="#8DDCFF" />}
        <Text style={s.footer}>Biometric recovery works only on the Android device where it is enrolled. Removing app data or changing enrolled biometrics may invalidate its protected credential. Keep your current password until enrollment has been tested successfully.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#05080D' },
  container: { padding: 18, paddingBottom: 36 },
  title: { color: '#F1F7FF', fontSize: 20, fontWeight: '900', letterSpacing: 2 },
  subtitle: { color: '#8CB8D1', fontSize: 11, marginTop: 6, marginBottom: 18 },
  statusCard: { backgroundColor: '#0D1A27', borderColor: '#31546D', borderWidth: 1, borderRadius: 14, padding: 14, marginBottom: 16 },
  statusTitle: { color: '#8DDAFF', fontSize: 11, fontWeight: '900', letterSpacing: 1 },
  statusText: { color: '#EAF4FC', fontSize: 13, lineHeight: 19, marginTop: 7 },
  card: { backgroundColor: '#0B131E', borderColor: '#2B4356', borderWidth: 1, borderRadius: 16, padding: 15, marginBottom: 14 },
  label: { color: '#9BCDE7', fontSize: 10, fontWeight: '800', letterSpacing: 1, marginTop: 9, marginBottom: 7 },
  input: { color: '#F1F8FF', backgroundColor: '#111D2A', borderColor: '#38546A', borderWidth: 1, borderRadius: 10, padding: 12, fontSize: 14 },
  primary: { backgroundColor: '#8DDCFF', borderRadius: 10, padding: 13, alignItems: 'center', marginTop: 13 },
  primaryText: { color: '#06111C', fontSize: 11, fontWeight: '900', letterSpacing: 1 },
  secondary: { backgroundColor: '#173047', borderColor: '#4B7797', borderWidth: 1, borderRadius: 10, padding: 13, alignItems: 'center', marginTop: 13 },
  secondaryText: { color: '#BDEBFF', fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  hint: { color: '#90A4B7', fontSize: 11, lineHeight: 17, marginTop: 13 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  section: { color: '#9BCDE7', fontSize: 11, fontWeight: '900', letterSpacing: 1.5 },
  logout: { color: '#FFB7A9', fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  actionCard: { backgroundColor: '#0B131E', borderColor: '#2B4356', borderWidth: 1, borderRadius: 14, padding: 14, marginBottom: 11 },
  actionHeading: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  actionName: { color: '#F1F7FF', fontSize: 14, fontWeight: '800', flex: 1 },
  risk: { color: '#FFD18A', fontSize: 9, fontWeight: '900', marginLeft: 8 },
  permission: { color: '#8FA9BD', fontSize: 10, marginTop: 8 },
  disabled: { opacity: 0.45 },
  loader: { marginTop: 16 },
  footer: { color: '#71899E', fontSize: 10, lineHeight: 16, marginTop: 20 },
});
