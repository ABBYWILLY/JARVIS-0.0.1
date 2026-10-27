"""Original, asset-free GLSL sources for the optional GPU reactor prototype."""

FULLSCREEN_VERTEX = """#version 330
out vec2 uv;
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    uv = p;
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
"""

# A small analytic camera/sphere model is shared by every luminous layer.
# No depth texture or raymarch is needed: rings are ray/plane intersections,
# and the near sphere hit determines whether a world-space stroke is in front.
SPACE_GLSL = """
const float CAMERA_Z = 2.6;
const float CORE_RADIUS = .30;
vec2 project_world(vec3 p) { return p.xy * CAMERA_Z / (CAMERA_Z-p.z); }
vec2 scene_plane(vec2 ndc, vec2 size) {
    float aspect = size.x/size.y;
    return ndc*vec2(aspect,1.0)/min(1.0,aspect);
}
vec2 plane_ndc(vec2 p, vec2 size) {
    float aspect = size.x/size.y;
    return p*min(1.0,aspect)/vec2(aspect,1.0);
}
float core_front(vec2 p) {
    float a = dot(p,p)+CAMERA_Z*CAMERA_Z;
    float b = -CAMERA_Z*CAMERA_Z;
    float c = CAMERA_Z*CAMERA_Z-CORE_RADIUS*CORE_RADIUS;
    float discriminant = b*b-a*c;
    return discriminant >= 0.0 ? (-b-sqrt(max(0.0,discriminant)))/a : 10000.0;
}
// Three related, separated orbital planes replace the crowded cage.
void orbit_axes(float ring, float time_s, out vec3 axis_u, out vec3 axis_v) {
    float rot = -.34+ring*.13+.055*sin(time_s*.16+ring);
    float cosine = .30+ring*.11+.018*sin(time_s*.19+ring*1.7);
    float sine = sqrt(1.0-cosine*cosine);
    axis_u = vec3(cos(rot),sin(rot),0.0);
    axis_v = vec3(-sin(rot)*cosine,cos(rot)*cosine,sine);
}
float visible_depth(float near_hit, float world_z, float activation) {
    if (activation <= 0.0 || near_hit > 2.0) return 1.0;
    float sample_hit = (CAMERA_Z-world_z)/CAMERA_Z;
    float visible = smoothstep(sample_hit-.0008,sample_hit+.0008,near_hit);
    return mix(1.0,visible,smoothstep(.1,.9,activation));
}
"""

REACTOR_FRAGMENT = """#version 330
in vec2 uv;
out vec4 frag;
uniform vec2 u_size;
uniform vec3 u_color;
uniform float u_time, u_reactor, u_rms;
""" + SPACE_GLSL + """
const float TAU = 6.28318530718;
float lineGlow(float d, float width) { return exp(-d*d/(width*width)); }
void main() {
    // Object light is added onto exact black, never an ambient background.
    vec3 light = vec3(0.0);
    if (u_reactor <= 0.0) { frag = vec4(light,1.0); return; }
    vec2 p = scene_plane(uv*2.0-1.0,u_size);
    float r = length(p), t = u_time;
    float activation = smoothstep(0.0,.85,u_reactor);
    float px = 2.0/min(u_size.x,u_size.y);
    float near_hit = core_front(p);
    vec3 cold = mix(u_color,vec3(.53,.83,1.0),.12);
    float breath = 1.0+.035*sin(t*1.7)+.10*u_rms;
    // A directional, emissive surface gives the same core material and volume.
    // Three bounded sine fields form flowing energy veins, without textures.
    light += cold*.045*exp(-r*r/.065)*(1.0-smoothstep(.42,.76,r))*activation;
    if (near_hit < 2.0) {
        vec3 surface = vec3(p*near_hit,CAMERA_Z*(1.0-near_hit));
        vec3 normal = surface/CORE_RADIUS;
        float lit = max(0.0,dot(normal,normalize(vec3(-.45,.6,1.0))));
        float field = sin(normal.x*17.0+t*.65+sin(normal.y*11.0-t*.43)*1.2)
                    +.52*sin(normal.z*21.0+normal.y*13.0-t*.56);
        float veins = pow(max(0.0,1.0-abs(field)*1.08),8.0);
        float rim = pow(max(0.0,1.0-normal.z),1.7);
        float scan = .82+.18*cos(normal.y*76.0-t*.8);
        float glint = pow(max(0.0,dot(reflect(normalize(vec3(.45,-.6,-1.0)),normal),
                                      vec3(0.0,0.0,1.0))),18.0);
        light += cold*(.035+.14*lit+.18*veins+.32*rim)*scan*breath*activation;
        light += mix(cold,vec3(.8,.96,1.0),.5)*glint*.22*activation;
    }
    float angle = atan(p.y,p.x);
    float shell = lineGlow(r-CORE_RADIUS-.0018*sin(angle*9.0-t*.8),.0015+px*.65);
    light += cold*shell*.32*activation;
    vec3 ray = vec3(p,-CAMERA_Z);
    // Exact ray/plane intersection: every circle has a world-space depth and
    // perspective foreshortening. Rear portions disappear behind the core.
    for (int i=0;i<3;++i) {
        float fi = float(i);
        vec3 axis_u, axis_v;
        orbit_axes(fi,t,axis_u,axis_v);
        vec3 normal = cross(axis_u,axis_v);
        float denominator = dot(normal,ray);
        if (abs(denominator)<.015) continue;
        float hit = -CAMERA_Z*normal.z/denominator;
        if (hit<=0.0) continue;
        vec3 world = vec3(p*hit,CAMERA_Z*(1.0-hit));
        vec2 q = vec2(dot(world,axis_u),dot(world,axis_v));
        float a = atan(q.y,q.x);
        float radius = .48+fi*.11;
        float d = length(q)-radius;
        // Bound derivatives at grazing ray/plane intersections: the
        // singularity must not paint a false halo into empty black space.
        float pixel_width = clamp(fwidth(length(q)),px*.42,px*2.5);
        float depth = clamp(.5+.5*world.z/radius,0.0,1.0);
        float phase = a+t*(.12+fi*.035)*(mod(fi,2.0)*2.0-1.0)+fi;
        float segment = .62+.38*pow(.5+.5*cos(phase),3.0);
        float width = .0008+pixel_width*(.48+depth*.18);
        float rail = lineGlow(d,width)*segment;
        float halo = lineGlow(d,.010+pixel_width)*.055*segment;
        float highlight = pow(max(0.0,cos(phase*2.0+fi)),18.0);
        float packet = pow(max(0.0,cos(phase*3.0+fi)),95.0);
        float visible = visible_depth(near_hit,world.z,u_reactor);
        light += cold*(rail*(.18+depth*.68+highlight*.28)+halo*.45
                       +lineGlow(d,.004+pixel_width)*packet*(.10+depth*.25))
                      *activation*visible;
    }
    frag = vec4(light,1.0);
}
"""

CURVE_VERTEX = """#version 330
in vec2 a_start, a_end, a_range;
in float a_main;
uniform vec2 u_size;
uniform float u_reactor, u_time, u_rms, u_detail_opacity;
out vec2 v_local;
flat out float v_length, v_strength, v_depth;
""" + SPACE_GLSL + """
vec3 position(vec2 source,float u) {
    if (a_main<.5 || u_reactor<=0.0) return vec3(source,.4);
    float a = u*25.13274123-u_time*.32;
    float radius = .024+.17*u;
    vec3 world = vec3(cos(a)*radius,sin(a)*radius*.82,.13*sin(a*.5)+.09);
    vec2 spiral = plane_ndc(project_world(world),u_size);
    float activation = smoothstep(0.0,1.0,u_reactor);
    return vec3(mix(source,spiral,activation),mix(.4,world.z,activation));
}
void main() {
    vec3 first = position(a_start,a_range.x), last = position(a_end,a_range.y);
    vec2 start = first.xy*u_size*.5, end = last.xy*u_size*.5;
    vec2 delta = end-start;
    float length_ = length(delta);
    vec2 tangent = length_>.0001 ? delta/length_ : vec2(1.0,0.0);
    vec2 normal = vec2(-tangent.y,tangent.x);
    float side = (gl_VertexID & 1)==0 ? -1.0 : 1.0;
    float along = gl_VertexID<2 ? -10.0 : length_+10.0;
    vec2 pixel = start+tangent*along+normal*side*10.0;
    gl_Position = vec4(pixel*2.0/u_size,0.0,1.0);
    v_local = vec2(along,side*10.0);
    v_length = length_;
    v_depth = (first.z+last.z)*.5;
    // The supplied PCM/symbol stays authoritative outside the reactor.
    // Its transitional spiral fades away before the sphere takes prominence.
    v_strength = a_main>.5 ? (1.0-smoothstep(.15,.85,u_reactor))
                          : (1.0-smoothstep(0.0,.8,u_reactor))*u_detail_opacity;
}
"""

CURVE_FRAGMENT = """#version 330
in vec2 v_local;
flat in float v_length, v_strength, v_depth;
uniform vec3 u_color;
uniform vec2 u_size;
uniform float u_rms, u_reactor;
out vec4 frag;
""" + SPACE_GLSL + """
void main() {
    float d = length(vec2(v_local.x-clamp(v_local.x,0.0,v_length),v_local.y));
    float core = exp(-d*d/.62);
    float shoulder = exp(-d*d/3.2)*.26;
    float halo = exp(-d*d/24.0)*.024;
    vec2 p = scene_plane(gl_FragCoord.xy*2.0/u_size-1.0,u_size);
    float visible = u_reactor<=0.0 ? 1.0 : visible_depth(core_front(p),v_depth,u_reactor);
    vec3 tint = mix(u_color,vec3(1.0),.16);
    frag = vec4(tint*(core*1.45+shoulder+halo)*(1.0+.4*u_rms)*v_strength*visible,1.0);
}
"""

FILAMENT_VERTEX = """#version 330
uniform vec2 u_size;
uniform float u_time, u_reactor, u_rms;
out vec2 v_local;
flat out float v_length, v_strength, v_depth;
""" + SPACE_GLSL + """
const int STEPS = 72;
vec3 path(float u,float strand) {
    float t = u_time;
    float theta = u*6.2831853+strand*1.04719755;
    float a = theta*2.0+t*(.21+strand*.018);
    float radius = .235+.038*sin(theta*3.0+t*.43+strand);
    vec3 p = vec3(cos(a)*radius,sin(a)*radius,.16*sin(theta+strand*.7));
    float tilt = .65+strand*.29;
    p.yz = mat2(cos(tilt),-sin(tilt),sin(tilt),cos(tilt))*p.yz;
    p.xy = mat2(cos(strand*.51),-sin(strand*.51),sin(strand*.51),cos(strand*.51))*p.xy;
    return p;
}
void main() {
    float strand = float(gl_InstanceID/STEPS);
    float u = float(gl_InstanceID%STEPS)/float(STEPS);
    vec3 first = path(u,strand), last = path(u+1.0/float(STEPS),strand);
    vec2 start = plane_ndc(project_world(first),u_size)*u_size*.5;
    vec2 end = plane_ndc(project_world(last),u_size)*u_size*.5;
    vec2 delta = end-start;
    float length_ = length(delta);
    vec2 tangent = normalize(delta+vec2(.00001,0.0));
    vec2 normal = vec2(-tangent.y,tangent.x);
    float side = (gl_VertexID & 1)==0 ? -1.0 : 1.0;
    float along = gl_VertexID<2 ? -5.0 : length_+5.0;
    gl_Position = vec4((start+tangent*along+normal*side*5.0)*2.0/u_size,0.0,1.0);
    v_local = vec2(along,side*5.0);
    v_length = length_;
    v_depth = (first.z+last.z)*.5;
    v_strength = u_reactor*u_rms*.08*(.4+.6*pow(.5+.5*sin(u*31.4159-u_time*.7+strand),2.0));
}
"""

PARTICLE_VERTEX = """#version 330
uniform vec2 u_size;
uniform float u_time, u_reactor, u_rms;
out float v_power, v_warm;
flat out float v_depth;
""" + SPACE_GLSL + """
float hash(float n) { return fract(sin(n*127.1+311.7)*43758.5453); }
void main() {
    float id = float(gl_VertexID), seed = hash(id+1.0);
    float ring = mod(id,3.0);
    float radius = .48+ring*.11;
    float a = seed*6.2831853+u_time*(.05+ring*.025);
    vec3 axis_u, axis_v;
    orbit_axes(ring,u_time,axis_u,axis_v);
    vec3 p = radius*(cos(a)*axis_u+sin(a)*axis_v);
    vec2 projected = plane_ndc(project_world(p),u_size);
    gl_Position = vec4(projected,0.0,1.0);
    float twinkle = pow(.5+.5*sin(u_time*(.5+seed)+id),5.0);
    gl_PointSize = (1.5+hash(id+6.0)*1.3)*(1.0+u_rms*.3)*CAMERA_Z/(CAMERA_Z-p.z);
    v_power = (.10+.22*twinkle)*u_reactor*(.65+p.z);
    v_warm = 0.0;
    v_depth = p.z;
}
"""

PARTICLE_FRAGMENT = """#version 330
in float v_power, v_warm;
flat in float v_depth;
uniform vec3 u_color;
uniform vec2 u_size;
uniform float u_reactor;
out vec4 frag;
""" + SPACE_GLSL + """
void main() {
    vec2 p = gl_PointCoord*2.0-1.0;
    float r2 = dot(p,p);
    if (r2>1.0) discard;
    vec2 screen_p = scene_plane(gl_FragCoord.xy*2.0/u_size-1.0,u_size);
    float visible = visible_depth(core_front(screen_p),v_depth,u_reactor);
    vec3 tint = mix(u_color,vec3(1.0,.53,.24),v_warm*.85);
    frag = vec4(tint*exp(-r2*5.5)*v_power*2.1*visible,1.0);
}
"""

EXTRACT_FRAGMENT = """#version 330
in vec2 uv;
uniform sampler2D u_image;
uniform vec2 u_source_size;
out vec4 frag;
void main() {
    vec3 light = vec3(0.0);
    for (int y=0;y<4;++y) for (int x=0;x<4;++x) {
        vec2 offset = (vec2(x,y)-1.5)/u_source_size;
        vec3 c = texture(u_image,uv+offset).rgb;
        float peak = max(c.r,max(c.g,c.b));
        light += c*smoothstep(.15,1.15,peak);
    }
    frag = vec4(light/16.0,1.0);
}
"""

BLUR_FRAGMENT = """#version 330
in vec2 uv;
uniform sampler2D u_image;
uniform vec2 u_step;
out vec4 frag;
void main() {
    vec3 c = texture(u_image,uv).rgb*.227027;
    c += (texture(u_image,uv+u_step*1.384615).rgb + texture(u_image,uv-u_step*1.384615).rgb)*.316216;
    c += (texture(u_image,uv+u_step*3.230769).rgb + texture(u_image,uv-u_step*3.230769).rgb)*.070270;
    frag = vec4(c,1.0);
}
"""

RESOLVE_FRAGMENT = """#version 330
in vec2 uv;
uniform sampler2D u_image, u_bloom;
uniform float u_bloom_amount;
out vec4 frag;
void main() {
    vec3 light = texture(u_image,uv).rgb + texture(u_bloom,uv).rgb*u_bloom_amount;
    vec3 mapped = 1.0-exp(-light*.88);
    frag = vec4(pow(max(mapped,vec3(0.0)),vec3(1.0/2.2)),1.0);
}
"""

COPY_FRAGMENT = """#version 330
in vec2 uv;
uniform sampler2D u_image;
out vec4 frag;
void main() { frag = vec4(texture(u_image,uv).rgb,1.0); }
"""
