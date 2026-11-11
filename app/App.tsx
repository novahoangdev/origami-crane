import { StatusBar } from "expo-status-bar";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { CraneScene } from "./src/scene/CraneScene";

export default function App() {
  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: "#fdf0d7" }}>
      <StatusBar hidden />
      <CraneScene />
    </GestureHandlerRootView>
  );
}
