import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./app/Layout";
import BookshelfPage from "./features/bookshelf/BookshelfPage";
import CourseDetailPage from "./features/course/CourseDetailPage";
import OnboardingPage from "./features/onboarding/OnboardingPage";

function OnboardingGuard({ children }: { children: React.ReactNode }) {
  const onboardingDone = localStorage.getItem("foxsay_onboarding_done");
  if (onboardingDone !== "true") {
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
