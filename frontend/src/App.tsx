import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./app/Layout";
import BookshelfPage from "./features/bookshelf/BookshelfPage";
import CourseDetailPage from "./features/course/CourseDetailPage";
import OnboardingPage from "./features/onboarding/OnboardingPage";
import { api } from "./shared/api";

function OnboardingGuard({ children }: { children: React.ReactNode }) {
  const [skipOnboarding, setSkipOnboarding] = useState<boolean | null>(null);

  useEffect(() => {
    // If onboarding already done, skip
    if (localStorage.getItem("foxsay_onboarding_done") === "true") {
      setSkipOnboarding(true);
      return;
    }
    // If backend already has courses, skip onboarding
    api.get<Array<{ id: string }>>("/courses")
      .then((courses) => {
        if (courses.length > 0) {
          localStorage.setItem("foxsay_onboarding_done", "true");
          setSkipOnboarding(true);
        } else {
          setSkipOnboarding(false);
        }
      })
      .catch(() => setSkipOnboarding(false));
  }, []);

  // Loading state
  if (skipOnboarding === null) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="w-8 h-8 border-2 border-foxAmber border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!skipOnboarding) {
    return <OnboardingPage />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route
            path="/"
            element={
              <OnboardingGuard>
                <BookshelfPage />
              </OnboardingGuard>
            }
          />
          <Route path="/courses/:courseId" element={<CourseDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
