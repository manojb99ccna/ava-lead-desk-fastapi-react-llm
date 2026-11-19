import { Navigate, Route, Routes } from 'react-router-dom'
import MainLayout from '../layouts/MainLayout.jsx'
import AdminLayout from '../layouts/AdminLayout.jsx'
import ProtectedRoute from './ProtectedRoute.jsx'
import Home from '../pages/Home.jsx'
import Login from '../pages/admin/Login.jsx'
import Dashboard from '../pages/admin/Dashboard.jsx'
import Leads from '../pages/admin/Leads.jsx'
import Appointments from '../pages/admin/Appointments.jsx'
import Conversations from '../pages/admin/Conversations.jsx'
import Faqs from '../pages/admin/Faqs.jsx'
import Customers from '../pages/admin/Customers.jsx'
import Business from '../pages/admin/Business.jsx'
import Handoffs from '../pages/admin/Handoffs.jsx'
import Users from '../pages/admin/Users.jsx'
import { getAdmin } from '../services/auth.js'

function AdminOnly({ children }) {
  return getAdmin()?.role === 'admin' ? children : <Navigate to="/admin" replace />
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/" element={<Home />} />
      </Route>

      <Route path="/admin/login" element={<Login />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AdminLayout />}>
          <Route path="/admin" element={<Dashboard />} />
          <Route path="/admin/appointments" element={<Appointments />} />
          <Route path="/admin/handoffs" element={<Handoffs />} />
          <Route path="/admin/leads" element={<Leads />} />
          <Route path="/admin/customers" element={<Customers />} />
          <Route path="/admin/conversations" element={<Conversations />} />
          <Route path="/admin/faqs" element={<Faqs />} />
          <Route path="/admin/business" element={<Business />} />
          <Route path="/admin/users" element={<AdminOnly><Users /></AdminOnly>} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
