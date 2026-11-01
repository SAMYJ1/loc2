import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
let size = 1024
let context = CGContext(data:nil,width:size,height:size,bitsPerComponent:8,bytesPerRow:size*4,
                        space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.noneSkipLast.rawValue)!
func color(_ r:CGFloat,_ g:CGFloat,_ b:CGFloat,_ a:CGFloat = 1) -> CGColor { CGColor(red:r,green:g,blue:b,alpha:a) }
context.setFillColor(color(0.035,0.14,0.19));context.fill(CGRect(x:0,y:0,width:size,height:size))
context.setStrokeColor(color(0.15,0.72,0.69,0.17));context.setLineWidth(8)
for v in stride(from:128,through:896,by:192) {
    context.move(to:CGPoint(x:v,y:0));context.addLine(to:CGPoint(x:v,y:1024))
    context.move(to:CGPoint(x:0,y:v));context.addLine(to:CGPoint(x:1024,y:v))
};context.strokePath()
context.setShadow(offset:CGSize(width:0,height:-18),blur:32,color:color(0,0,0,0.25))
let pin = CGMutablePath();pin.move(to:CGPoint(x:512,y:170))
pin.addCurve(to:CGPoint(x:260,y:605),control1:CGPoint(x:440,y:270),control2:CGPoint(x:260,y:427))
pin.addCurve(to:CGPoint(x:764,y:605),control1:CGPoint(x:260,y:946),control2:CGPoint(x:764,y:946))
pin.addCurve(to:CGPoint(x:512,y:170),control1:CGPoint(x:764,y:427),control2:CGPoint(x:584,y:270))
pin.closeSubpath();context.addPath(pin);context.setFillColor(color(0.28,0.91,0.79));context.fillPath()
context.setShadow(offset:.zero,blur:0,color:nil)
context.setFillColor(color(0.035,0.14,0.19));context.fillEllipse(in:CGRect(x:398,y:512,width:228,height:228))
context.setFillColor(color(1,1,1));context.fillEllipse(in:CGRect(x:474,y:588,width:76,height:76))
let destination = CGImageDestinationCreateWithURL(URL(fileURLWithPath:CommandLine.arguments[1]) as CFURL,UTType.png.identifier as CFString,1,nil)!
CGImageDestinationAddImage(destination,context.makeImage()!,nil)
precondition(CGImageDestinationFinalize(destination))
