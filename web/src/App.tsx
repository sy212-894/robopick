import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import Demo from './pages/Demo'
import Results from './pages/Results'
import Runs from './pages/Runs'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="demo" element={<Demo />} />
        <Route path="results" element={<Results />} />
        <Route path="runs" element={<Runs />} />
      </Route>
    </Routes>
  )
}
