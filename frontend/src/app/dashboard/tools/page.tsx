import { Checkins, Flashcards, Pomodoro } from "@/components/study-tools";

export default function ToolsPage() {
  return (
    <div className="space-y-6">
      <Flashcards />
      <div className="grid gap-6 md:grid-cols-2">
        <Pomodoro />
        <Checkins />
      </div>
    </div>
  );
}
