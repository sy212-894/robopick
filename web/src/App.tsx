import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import Demo from './pages/Demo'
import Datasets from './pages/Datasets'
import Dataset from './pages/Dataset'
import Runs from './pages/Runs'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="select" element={<Demo />} />
        <Route path="datasets" element={<Datasets />} />
        <Route path="datasets/:id" element={<Dataset />} />
        <Route path="runs" element={<Runs />} />
        {/* 예전 주소: 데모 → 선별하기, 실험 결과 → 데이터셋 상세 */}
        <Route path="demo" element={<Navigate to="/select" replace />} />
        <Route path="results" element={<Navigate to="/datasets/can_mh" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
