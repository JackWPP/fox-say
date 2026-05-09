import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./app/Layout";
import BookshelfPage from "./features/bookshelf/BookshelfPage";
import CourseDetailPage from "./features/course/CourseDetailPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<BookshelfPage />} />
          <Route path="/courses/:courseId" element={<CourseDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
