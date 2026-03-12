import React, {useRef, useEffect, useState, useCallback} from 'react';
import {
  StatusBar,
  StyleSheet,
  PermissionsAndroid,
  Platform,
  BackHandler,
  Text,
  View,
  ActivityIndicator,
  TouchableOpacity,
} from 'react-native';
import {SafeAreaProvider, SafeAreaView} from 'react-native-safe-area-context';
import {WebView, WebViewNavigation} from 'react-native-webview';
import Config from 'react-native-config';

const WEBAPP_URL = Config.WEBAPP_URL || 'https://voiceagent.xappy.io';

function App() {
  const webViewRef = useRef<WebView>(null);
  const [micGranted, setMicGranted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    (async () => {
      if (Platform.OS === 'android') {
        const granted = await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
          {
            title: 'Microphone Permission',
            message: 'UBudy needs microphone access for voice chat.',
            buttonPositive: 'Allow',
          },
        );
        setMicGranted(granted === PermissionsAndroid.RESULTS.GRANTED);
      } else {
        setMicGranted(true);
      }
    })();
  }, []);

  useEffect(() => {
    const onBackPress = () => {
      if (webViewRef.current) {
        webViewRef.current.goBack();
        return true;
      }
      return false;
    };
    BackHandler.addEventListener('hardwareBackPress', onBackPress);
    return () =>
      BackHandler.removeEventListener('hardwareBackPress', onBackPress);
  }, []);

  const handleRetry = useCallback(() => {
    setError(false);
    setLoading(true);
    webViewRef.current?.reload();
  }, []);

  if (!micGranted) {
    return (
      <View style={styles.centerContainer}>
        <StatusBar barStyle="light-content" backgroundColor="#0a0a0f" />
        <ActivityIndicator size="large" color="#a78bfa" />
        <Text style={styles.statusText}>Requesting microphone permission...</Text>
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <StatusBar barStyle="light-content" backgroundColor="#0a0a0f" />
      <SafeAreaView style={styles.container} edges={['top']}>
        <WebView
          ref={webViewRef}
          source={{uri: WEBAPP_URL}}
          style={styles.webview}
          javaScriptEnabled={true}
          domStorageEnabled={true}
          mediaPlaybackRequiresUserAction={false}
          allowsInlineMediaPlayback={true}
          mediaCapturePermissionGrantType="grant"
          allowFileAccess={true}
          mixedContentMode="compatibility"
          onLoadStart={() => {
            setLoading(true);
            setError(false);
          }}
          onLoadEnd={() => setLoading(false)}
          onError={() => {
            setLoading(false);
            setError(true);
          }}
          onHttpError={(syntheticEvent) => {
            const {statusCode} = syntheticEvent.nativeEvent;
            if (statusCode >= 500) {
              setError(true);
            }
          }}
        />
        {loading && !error && (
          <View style={styles.overlay}>
            <ActivityIndicator size="large" color="#a78bfa" />
            <Text style={styles.statusText}>Loading UBudy...</Text>
          </View>
        )}
        {error && (
          <View style={styles.overlay}>
            <Text style={styles.errorEmoji}>!</Text>
            <Text style={styles.errorText}>Could not connect to server</Text>
            <Text style={styles.errorSub}>Make sure the backend is running</Text>
            <TouchableOpacity style={styles.retryButton} onPress={handleRetry}>
              <Text style={styles.retryText}>Retry</Text>
            </TouchableOpacity>
          </View>
        )}
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0a0a0f',
  },
  centerContainer: {
    flex: 1,
    backgroundColor: '#0a0a0f',
    justifyContent: 'center',
    alignItems: 'center',
  },
  webview: {
    flex: 1,
    backgroundColor: '#0a0a0f',
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: '#0a0a0f',
    justifyContent: 'center',
    alignItems: 'center',
  },
  statusText: {
    color: '#a78bfa',
    fontSize: 16,
    marginTop: 16,
  },
  errorEmoji: {
    fontSize: 48,
    color: '#a78bfa',
    fontWeight: 'bold',
    marginBottom: 12,
  },
  errorText: {
    color: '#ffffff',
    fontSize: 18,
    fontWeight: '600',
  },
  errorSub: {
    color: '#888',
    fontSize: 14,
    marginTop: 8,
  },
  retryButton: {
    marginTop: 24,
    backgroundColor: '#a78bfa',
    paddingHorizontal: 32,
    paddingVertical: 12,
    borderRadius: 24,
  },
  retryText: {
    color: '#0a0a0f',
    fontSize: 16,
    fontWeight: '600',
  },
});

export default App;
